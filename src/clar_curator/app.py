"""
CLAR Curator — Workday Studio .clar Generator
Run with:  streamlit run src/clar_curator/app.py
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import streamlit as st

from clar_curator.generator.clar_generator import (
    IntegrationSpec,
    LaunchParam,
    ServiceAttribute,
    generate,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="CLAR Curator",
    page_icon="⚙️",
    layout="centered",
)

st.title("⚙️ CLAR Curator")
st.caption("Fill in the details below and download a ready-to-import Workday Studio `.clar` file.")

# ---------------------------------------------------------------------------
# Auth attribute presets per transmission method
# ---------------------------------------------------------------------------

AUTH_PRESETS: dict[str, list[dict]] = {
    "REST API — OAuth 2.0 (Client Credentials)": [
        {"name": "URL Endpoint",   "type": "text",  "password": False, "required": False},
        {"name": "Client ID",      "type": "text",  "password": False, "required": False},
        {"name": "Client Secret",  "type": "text",  "password": True,  "required": False},
        {"name": "Refresh Token",  "type": "text",  "password": True,  "required": True},
    ],
    "REST API — API Key": [
        {"name": "URL Endpoint",   "type": "text",  "password": False, "required": False},
        {"name": "API Key",        "type": "text",  "password": True,  "required": True},
    ],
    "REST API — Basic Auth": [
        {"name": "URL Endpoint",   "type": "text",  "password": False, "required": False},
        {"name": "Username",       "type": "text",  "password": False, "required": False},
        {"name": "Password",       "type": "text",  "password": True,  "required": True},
    ],
    "SOAP API": [
        {"name": "WSDL URL",       "type": "text",  "password": False, "required": False},
        {"name": "Username",       "type": "text",  "password": False, "required": False},
        {"name": "Password",       "type": "text",  "password": True,  "required": True},
    ],
    "SFTP": [
        {"name": "Host",           "type": "text",  "password": False, "required": False},
        {"name": "Port",           "type": "number","password": False, "required": False},
        {"name": "Remote Path",    "type": "text",  "password": False, "required": False},
        {"name": "Username",       "type": "text",  "password": False, "required": False},
        {"name": "Password",       "type": "text",  "password": True,  "required": True},
    ],
    "FTP / FTPS": [
        {"name": "Host",           "type": "text",  "password": False, "required": False},
        {"name": "Port",           "type": "number","password": False, "required": False},
        {"name": "Remote Path",    "type": "text",  "password": False, "required": False},
        {"name": "Username",       "type": "text",  "password": False, "required": False},
        {"name": "Password",       "type": "text",  "password": True,  "required": True},
    ],
    "Workday EIB / RaaS": [
        {"name": "Report URL",     "type": "text",  "password": False, "required": False},
        {"name": "WWS Version",    "type": "text",  "password": False, "required": False},
    ],
    "Custom / Other": [],
}

DEFAULT_DATE_PARAMS = [
    LaunchParam(
        name="Effective Date",
        type="date",
        default_wid="52f526bab1d84191ac96f44a6c37c484",
        default_desc="Current Effective Date",
    ),
    LaunchParam(
        name="From Effective Date",
        type="date",
        default_wid="117071710a61418db408deb128d27875",
        default_desc="As Of Effective Date of Last Completed Integration Event",
    ),
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _to_safe_name(*parts: str) -> str:
    """Join parts into a safe integration name, e.g. 'Greenhouse Hire Inbound'."""
    combined = "_".join(p.strip() for p in parts if p.strip())
    return re.sub(r"[^A-Za-z0-9_]", "_", combined).strip("_")


# ---------------------------------------------------------------------------
# Section 1 — Integration basics
# ---------------------------------------------------------------------------

st.header("1. Integration Details")

col1, col2 = st.columns(2)
with col1:
    vendor = st.text_input("Vendor / System Name *", placeholder="e.g. Greenhouse, Concur, ADP")
with col2:
    process = st.text_input("Process / Topic", placeholder="e.g. Hire, Payroll (optional)")

col3, col4 = st.columns(2)
with col3:
    direction = st.selectbox("Direction *", ["Inbound", "Outbound", "Bidirectional"])
with col4:
    method = st.selectbox(
        "Transmission Method *",
        list(AUTH_PRESETS.keys()),
    )

# Auto-build name
safe_vendor  = re.sub(r"\s+", "_", vendor.strip())
safe_process = re.sub(r"\s+", "_", process.strip())
auto_name    = _to_safe_name(safe_vendor, safe_process, direction) if vendor else ""

col5, col6 = st.columns(2)
with col5:
    int_number = st.text_input("INT Number", placeholder="e.g. INT042")
with col6:
    tenant_prefix = st.text_input("Tenant Prefix", value="STU", placeholder="e.g. STU")

int_sys_name_default = " ".join(p for p in [int_number, tenant_prefix, vendor, process, direction] if p.strip())
int_sys_name = st.text_input(
    "Integration System Name",
    value=int_sys_name_default,
    help="The full name as it appears in Workday, e.g. 'INT042 STU Greenhouse Hire Inbound'",
)

svc_name_default = f"{safe_vendor}-Connection" if vendor else ""
attribute_map_service_name = st.text_input(
    "Attribute-Map Service Name",
    value=svc_name_default,
    help="Named service that holds connection attributes, e.g. 'Greenhouse-Connection'",
)

col7, col8 = st.columns(2)
with col7:
    author = st.text_input("Author", placeholder="Your name")
with col8:
    assembly_version = st.text_input("Assembly Version", value="2021.51")

description = st.text_area("Description", placeholder="Brief description of what this integration does")

# ---------------------------------------------------------------------------
# Section 2 — Connection attributes
# ---------------------------------------------------------------------------

st.header("2. Connection Attributes")
st.caption("Pre-populated based on your transmission method. Add or remove as needed.")

preset = AUTH_PRESETS[method]

# Session state for dynamic rows
if "attr_rows" not in st.session_state or st.session_state.get("last_method") != method:
    st.session_state.attr_rows = [dict(a) for a in preset]
    st.session_state.last_method = method

def _add_attr_row():
    st.session_state.attr_rows.append({"name": "", "type": "text", "password": False, "required": False})

def _remove_attr_row(i: int):
    st.session_state.attr_rows.pop(i)

for idx, row in enumerate(st.session_state.attr_rows):
    c1, c2, c3, c4, c5 = st.columns([3, 1.5, 1, 1, 0.5])
    with c1:
        st.session_state.attr_rows[idx]["name"] = st.text_input(
            "Attribute Name", value=row["name"], key=f"attr_name_{idx}", label_visibility="collapsed"
        )
    with c2:
        st.session_state.attr_rows[idx]["type"] = st.selectbox(
            "Type", ["text", "number", "boolean", "date"],
            index=["text", "number", "boolean", "date"].index(row.get("type", "text")),
            key=f"attr_type_{idx}", label_visibility="collapsed",
        )
    with c3:
        st.session_state.attr_rows[idx]["password"] = st.checkbox(
            "🔒 Secret", value=row.get("password", False), key=f"attr_pw_{idx}"
        )
    with c4:
        st.session_state.attr_rows[idx]["required"] = st.checkbox(
            "Req. at launch", value=row.get("required", False), key=f"attr_req_{idx}"
        )
    with c5:
        st.button("✕", key=f"del_attr_{idx}", on_click=_remove_attr_row, args=(idx,))

st.button("＋ Add attribute", on_click=_add_attr_row)

# ---------------------------------------------------------------------------
# Section 3 — Launch parameters
# ---------------------------------------------------------------------------

st.header("3. Launch Parameters")
st.caption("Parameters the user can set when launching the integration in Workday.")

include_date_params = st.checkbox("Include standard date range parameters (Effective Date / From Effective Date)", value=True)

if "lp_rows" not in st.session_state:
    st.session_state.lp_rows = []

def _add_lp_row():
    st.session_state.lp_rows.append({"name": "", "type": "text", "default_wid": "", "default_desc": ""})

def _remove_lp_row(i: int):
    st.session_state.lp_rows.pop(i)

if st.session_state.lp_rows:
    for idx, row in enumerate(st.session_state.lp_rows):
        c1, c2, c3 = st.columns([3, 2, 0.5])
        with c1:
            st.session_state.lp_rows[idx]["name"] = st.text_input(
                "Parameter Name", value=row["name"], key=f"lp_name_{idx}", label_visibility="collapsed", placeholder="e.g. Company"
            )
        with c2:
            st.session_state.lp_rows[idx]["type"] = st.selectbox(
                "Type", ["text", "date", "boolean", "number"],
                index=["text", "date", "boolean", "number"].index(row.get("type", "text")),
                key=f"lp_type_{idx}", label_visibility="collapsed",
            )
        with c3:
            st.button("✕", key=f"del_lp_{idx}", on_click=_remove_lp_row, args=(idx,))

st.button("＋ Add launch parameter", on_click=_add_lp_row)

# ---------------------------------------------------------------------------
# Section 4 — Generate
# ---------------------------------------------------------------------------

st.divider()

final_name = st.text_input(
    "Integration Name (file name)",
    value=auto_name,
    help="This becomes the .clar filename and integration identifier. Use underscores, no spaces.",
)

st.caption(f"Will generate: `{final_name}.clar`" if final_name else "Enter a vendor name above to auto-fill.")

if st.button("⬇️ Generate & Download .clar", type="primary", disabled=not final_name.strip()):

    # Build launch params
    launch_params: list[LaunchParam] = []
    if include_date_params:
        launch_params.extend(DEFAULT_DATE_PARAMS)
    for row in st.session_state.lp_rows:
        if row["name"].strip():
            launch_params.append(LaunchParam(name=row["name"].strip(), type=row["type"]))

    # Build service attributes
    attributes: list[ServiceAttribute] = []
    for row in st.session_state.attr_rows:
        if row["name"].strip():
            attributes.append(ServiceAttribute(
                name=row["name"].strip(),
                type=row.get("type", "text"),
                display_as_password=bool(row.get("password")),
                required_for_launch=bool(row.get("required")),
            ))

    spec = IntegrationSpec(
        name=final_name.strip(),
        description=description,
        author=author,
        assembly_version=assembly_version,
        int_sys_name=int_sys_name.strip() or final_name.strip(),
        attribute_map_service_name=attribute_map_service_name.strip() or f"{final_name}-Connection",
        launch_params=launch_params,
        attributes=attributes,
        delivery_type=method,
    )

    # Generate into a temp buffer
    tmp_path = Path(f"/tmp/{final_name}.clar")
    generate(spec, tmp_path)
    clar_bytes = tmp_path.read_bytes()

    st.success(f"✅ `{final_name}.clar` is ready!")
    st.download_button(
        label=f"📥 Download {final_name}.clar",
        data=clar_bytes,
        file_name=f"{final_name}.clar",
        mime="application/zip",
    )

    # Quick preview
    with st.expander("Preview archive contents"):
        with zipfile.ZipFile(io.BytesIO(clar_bytes)) as zf:
            for name in sorted(zf.namelist()):
                st.text(f"  {name}")

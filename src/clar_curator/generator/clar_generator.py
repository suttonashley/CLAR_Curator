"""
Generate a .clar ZIP archive from a structured integration spec.

The file layout matches the structure reverse-engineered from real .clar samples:

    WorkdayManifest.xml
    binary/{name}/clar.xml
    binary/{name}/{name}/META-INF/MANIFEST.MF
    binary/{name}/{name}/WSAR-INF/assembly.xml
    binary/{name}/{name}/WSAR-INF/WriteConnectorXML.xsl  (if xslt provided)
    source/{name}/{name}/.classpath
    source/{name}/{name}/.project
    source/{name}/{name}/.settings/cc.facet.assembly.xml
    source/{name}/{name}/.settings/cc.ws.cloud.assembly.xml
    source/{name}/{name}/.settings/org.eclipse.core.resources.prefs
    source/{name}/{name}/.settings/org.eclipse.jdt.core.prefs
    source/{name}/{name}/.settings/org.eclipse.wst.common.component
    source/{name}/{name}/.settings/org.eclipse.wst.common.project.facet.core.xml
    source/{name}/{name}/ws/META-INF/MANIFEST.MF
    source/{name}/{name}/ws/WSAR-INF/assembly.xml
    source/{name}/{name}/ws/WSAR-INF/WriteConnectorXML.xsl  (if xslt provided)
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class LaunchParam:
    """A Workday integration launch parameter."""
    name: str
    type: str = "text"          # text | date | boolean | number
    default_wid: str = ""       # WID of the default class-report-field
    default_desc: str = ""      # Human-readable description of the default


@dataclass
class ServiceAttribute:
    """A named attribute on a cloud attribute-map-service."""
    name: str
    type: str = "text"          # text | number | boolean | date
    display_as_password: bool = False
    required_for_launch: bool = False


@dataclass
class IntegrationSpec:
    """
    A normalised description of a Workday Studio integration.

    This is the intermediate representation produced by the AI layer and
    consumed by the generator.
    """

    # Required
    name: str

    # Metadata
    description: str = ""
    author: str = ""
    assembly_version: str = "2021.51"

    # Integration system name as it appears in Workday
    int_sys_name: str = ""

    # Named attribute-map service (holds connection/config attributes)
    attribute_map_service_name: str = ""

    # Launch parameters shown when running the integration
    launch_params: list[LaunchParam] = field(default_factory=list)

    # Connection / configuration attributes on the attribute-map service
    attributes: list[ServiceAttribute] = field(default_factory=list)

    # XSLT transformation (raw XSL string); written as WriteConnectorXML.xsl
    xslt: str = ""

    # Provide a fully-formed assembly XML to override the generated skeleton
    assembly_xml: str = ""

    # Legacy fields kept for backwards compatibility with the AI layer
    source_system: str = ""
    target_system: str = ""
    version: str = "1.0"
    field_mappings: list[dict[str, str]] = field(default_factory=list)
    delivery_type: str = "HTTPS"
    delivery_config: dict[str, Any] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.int_sys_name:
            self.int_sys_name = self.name
        if not self.attribute_map_service_name:
            self.attribute_map_service_name = self.name


def generate(spec: IntegrationSpec, output_path: str | Path) -> Path:
    """
    Build a .clar ZIP archive from the given IntegrationSpec.

    Returns the path to the generated file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        _write_manifest(zf, spec)
        _write_clar_xml(zf, spec)
        _write_binary_files(zf, spec)
        _write_source_files(zf, spec)

    output_path.write_bytes(buf.getvalue())
    return output_path


# ---------------------------------------------------------------------------
# Top-level manifest
# ---------------------------------------------------------------------------

def _write_manifest(zf: zipfile.ZipFile, spec: IntegrationSpec) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")
    manifest = f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<wm:manifest xmlns:wm="http://www.workday.com/solution/catalog/manifest/10" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.workday.com/solution/catalog/manifest/10 http://www.workday.com/solution/catalog/manifest/10">

    <wm:clar version="3.0"/>

    <wm:descriptive>

        <wm:title>{_esc(spec.name)}</wm:title>

        <wm:description>{_esc(spec.description)}</wm:description>

        <wm:author>{_esc(spec.author)}</wm:author>

        <wm:timestamp>{ts}</wm:timestamp>

    </wm:descriptive>

</wm:manifest>
"""
    zf.writestr("WorkdayManifest.xml", manifest.encode("utf-8"))


# ---------------------------------------------------------------------------
# binary/{name}/clar.xml  — cloud-collection definition
# ---------------------------------------------------------------------------

def _write_clar_xml(zf: zipfile.ZipFile, spec: IntegrationSpec) -> None:
    attrs_xml = _render_attributes(spec.attributes, indent="    ")
    params_xml = _render_launch_params(spec.launch_params, indent="        ")

    service_ref = (
        f'\n        <cloud:service-reference name="{_esc(spec.attribute_map_service_name)}"/>'
        if spec.attributes
        else ""
    )

    attr_map_block = ""
    if spec.attributes:
        attr_map_block = f"""  <cloud:attribute-map-service name="{_esc(spec.attribute_map_service_name)}">
{attrs_xml}  </cloud:attribute-map-service>
  """

    clar_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<cloud:cloud-collection xmlns:cloud="urn:com.workday/esb/cloud/10.0" name="{_esc(spec.name)}">
  {attr_map_block}<cloud:integration name="{_esc(spec.name)}">
    <cloud:in-connector id="StartMain">
      <cloud:integration-system name="{_esc(spec.int_sys_name)}">
{params_xml}{service_ref}
      </cloud:integration-system>
    </cloud:in-connector>
  </cloud:integration>
  <cloud:deployed-by>nouser@notenant</cloud:deployed-by>
</cloud:cloud-collection>
"""
    zf.writestr(f"binary/{spec.name}/clar.xml", clar_xml.encode("utf-8"))


# ---------------------------------------------------------------------------
# binary/{name}/{name}/ files
# ---------------------------------------------------------------------------

def _write_binary_files(zf: zipfile.ZipFile, spec: IntegrationSpec) -> None:
    base = f"binary/{spec.name}/{spec.name}"

    zf.writestr(f"{base}/META-INF/MANIFEST.MF", b"Manifest-Version: 1.0\nClass-Path: \n")

    assembly = spec.assembly_xml if spec.assembly_xml else _generate_assembly_xml(spec)
    zf.writestr(f"{base}/WSAR-INF/assembly.xml", assembly.encode("utf-8"))

    if spec.xslt:
        zf.writestr(f"{base}/WSAR-INF/WriteConnectorXML.xsl", spec.xslt.encode("utf-8"))


# ---------------------------------------------------------------------------
# source/{name}/{name}/ files
# ---------------------------------------------------------------------------

def _write_source_files(zf: zipfile.ZipFile, spec: IntegrationSpec) -> None:
    base = f"source/{spec.name}/{spec.name}"

    zf.writestr(f"{base}/.classpath", _classpath_xml())
    zf.writestr(f"{base}/.project", _project_xml(spec.name))
    zf.writestr(f"{base}/.settings/cc.facet.assembly.xml", _cc_facet_assembly_xml())
    zf.writestr(f"{base}/.settings/cc.ws.cloud.assembly.xml", _cc_ws_cloud_assembly_xml(spec.name))
    zf.writestr(f"{base}/.settings/org.eclipse.core.resources.prefs", b"eclipse.preferences.version=1\nencoding/<project>=UTF-8\n")
    zf.writestr(f"{base}/.settings/org.eclipse.jdt.core.prefs", b"eclipse.preferences.version=1\norg.eclipse.jdt.core.compiler.source=1.8\n")
    zf.writestr(f"{base}/.settings/org.eclipse.wst.common.component", _wst_component_xml(spec.name))
    zf.writestr(f"{base}/.settings/org.eclipse.wst.common.project.facet.core.xml", _facet_core_xml())

    zf.writestr(f"{base}/ws/META-INF/MANIFEST.MF", b"Manifest-Version: 1.0\nClass-Path: \n")

    assembly = spec.assembly_xml if spec.assembly_xml else _generate_assembly_xml(spec)
    zf.writestr(f"{base}/ws/WSAR-INF/assembly.xml", assembly.encode("utf-8"))

    if spec.xslt:
        zf.writestr(f"{base}/ws/WSAR-INF/WriteConnectorXML.xsl", spec.xslt.encode("utf-8"))


# ---------------------------------------------------------------------------
# Assembly XML skeleton generator
# ---------------------------------------------------------------------------

def _generate_assembly_xml(spec: IntegrationSpec) -> str:
    """Generate a minimal but valid cc:assembly skeleton."""
    params_and_attrs = _render_launch_params(spec.launch_params, indent="        ")
    if spec.attributes:
        params_and_attrs += f"""        <cloud:attribute-map-service name="{_esc(spec.attribute_map_service_name)}">
{_render_attributes(spec.attributes, indent="          ")}        </cloud:attribute-map-service>
"""

    # Eval expressions for launch params
    lp_exprs = "\n".join(
        f"                    <cc:expression>props['lp.{_prop_key(p.name)}'] = lp.getSimpleData('{_esc(p.name)}')</cc:expression>"
        for p in spec.launch_params
    )
    lp_eval = ""
    if lp_exprs:
        lp_eval = f"""                <cc:eval id="LaunchParams">
{lp_exprs}
                </cc:eval>
"""

    # Error handler locals
    n = spec.name
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<beans
     xmlns="http://www.springframework.org/schema/beans"
     xmlns:beans="http://www.springframework.org/schema/beans"
     xmlns:atom="http://www.w3.org/2005/Atom"
     xmlns:cc="http://www.capeclear.com/assembly/10"
     xmlns:cloud="urn:com.workday/esb/cloud/10.0"
     xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"
     xmlns:pi="urn:com.workday/picof"
     xmlns:wd="urn:com.workday/bsvc"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">

    <cc:assembly id="WorkdayAssembly" version="{_esc(spec.assembly_version)}">
        <cc:workday-in id="StartMain" routes-to="CallInit">
            <cc:integration-system name="{_esc(spec.int_sys_name)}">
{params_and_attrs}            </cc:integration-system>
        </cc:workday-in>
        <cc:local-out id="CallInit" store-message="none" routes-response-to="PutIntegrationEvent" endpoint="vm://{_esc(n)}/Init"/>
        <cc:async-mediation id="InitMediation" handle-downstream-errors="true">
            <cc:steps>
{lp_eval}                <!-- TODO: add your integration logic steps here -->
            </cc:steps>
            <cc:send-error id="SendError" routes-to="CallInitMediationCriticalError"/>
        </cc:async-mediation>
        <cc:local-in id="Init" store-message="none" routes-to="InitMediation"/>
        <cc:local-out id="Put-GlobalError" endpoint="vm://wcc/PutIntegrationMessage">
            <cc:set name="is.message.severity" value="'CRITICAL'"/>
            <cc:set name="is.message.summary" value="'Encountered an unhandled or unexpected critical system error. Terminating Processing. ' # context.errorMessage"/>
            <cc:set name="is.message.storage.enabled" value="false"/>
        </cc:local-out>
        <cc:send-error id="GlobalErrorHandler" routes-to="Put-GlobalError"/>
        <cc:local-out id="PutIntegrationEvent" endpoint="vm://wcc/PutIntegrationEvent"/>
        <cc:local-out id="PutCriticalError" routes-response-to="PutIntegrationEvent" endpoint="vm://wcc/PutIntegrationMessage">
            <cc:set name="is.message.severity" value="props['error']"/>
            <cc:set name="is.message.summary" value="&quot;An unexpected error occurred. &quot; + context.errorMessage"/>
            <cc:set name="is.message.detail" value="context.errorMessage"/>
        </cc:local-out>
        <cc:async-mediation id="SetCriticalErrorFlag" routes-to="PutCriticalError" handle-downstream-errors="true">
            <cc:steps>
                <cc:eval id="SetErrorFlag">
                    <cc:expression>props['critical.error.occurred'] = true</cc:expression>
                    <cc:expression>props['error'] = props['error.level'] == 'WARNING' ? props['error.level'] : 'ERROR'</cc:expression>
                </cc:eval>
            </cc:steps>
        </cc:async-mediation>
        <cc:local-in id="CriticalError" routes-to="SetCriticalErrorFlag"/>
        <cc:local-out id="CallInitMediationCriticalError" store-message="none" endpoint="CriticalError"><cc:set name="step.id" value="'InitMediation'"/></cc:local-out>
    </cc:assembly>

</beans>
"""


# ---------------------------------------------------------------------------
# XML fragment renderers
# ---------------------------------------------------------------------------

def _render_launch_params(params: list[LaunchParam], indent: str = "") -> str:
    if not params:
        return ""
    lines = []
    for p in params:
        lines.append(f'{indent}<cloud:param name="{_esc(p.name)}">')
        lines.append(f"{indent}  <cloud:type>")
        lines.append(f"{indent}    <cloud:simple-type>{_esc(p.type)}</cloud:simple-type>")
        lines.append(f"{indent}  </cloud:type>")
        if p.default_wid:
            lines.append(f"{indent}  <cloud:default>")
            lines.append(
                f'{indent}    <cloud:class-report-field description="{_esc(p.default_desc)}" type="WID">{_esc(p.default_wid)}</cloud:class-report-field>'
            )
            lines.append(f"{indent}  </cloud:default>")
        lines.append(f"{indent}</cloud:param>")
    return "\n".join(lines) + "\n"


def _render_attributes(attrs: list[ServiceAttribute], indent: str = "") -> str:
    if not attrs:
        return ""
    lines = []
    for a in attrs:
        lines.append(f'{indent}<cloud:attribute name="{_esc(a.name)}">')
        lines.append(f"{indent}  <cloud:type>")
        lines.append(f"{indent}    <cloud:simple-type>{_esc(a.type)}</cloud:simple-type>")
        lines.append(f"{indent}  </cloud:type>")
        if a.display_as_password:
            lines.append(f"{indent}  <cloud:display-option>display-as-password</cloud:display-option>")
        if a.required_for_launch:
            lines.append(f"{indent}  <cloud:display-option>required-for-launch</cloud:display-option>")
        lines.append(f"{indent}</cloud:attribute>")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Eclipse / Workday Studio project scaffolding files
# ---------------------------------------------------------------------------

def _classpath_xml() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<classpath>
\t<classpathentry kind="src" path="src"/>
\t<classpathentry kind="con" path="org.eclipse.jdt.launching.JRE_CONTAINER"/>
\t<classpathentry kind="con" path="com.capeclear.wtp.ws.container">
\t\t<attributes>
\t\t\t<attribute name="org.eclipse.jst.component.nondependency" value=""/>
\t\t</attributes>
\t</classpathentry>
\t<classpathentry kind="con" path="org.eclipse.jst.server.core.container/com.workday.cloud.jst.server.runtimeTarget.wdscl/Workday Runtime">
\t\t<attributes>
\t\t\t<attribute name="owner.project.facets" value="cc.ws.cloud.assembly"/>
\t\t</attributes>
\t</classpathentry>
\t<classpathentry kind="output" path="build/classes"/>
</classpath>
"""


def _project_xml(name: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<projectDescription>
\t<name>{_esc(name)}</name>
\t<comment></comment>
\t<projects>
\t</projects>
\t<buildSpec>
\t\t<buildCommand>
\t\t\t<name>com.capeclear.wtp.facet.assembly.builder</name>
\t\t\t<arguments>
\t\t\t</arguments>
\t\t</buildCommand>
\t\t<buildCommand>
\t\t\t<name>org.eclipse.jdt.core.javabuilder</name>
\t\t\t<arguments>
\t\t\t</arguments>
\t\t</buildCommand>
\t\t<buildCommand>
\t\t\t<name>com.workday.wtp.ws.cloud.assembly.builder</name>
\t\t\t<arguments>
\t\t\t</arguments>
\t\t</buildCommand>
\t\t<buildCommand>
\t\t\t<name>org.eclipse.wst.common.project.facet.core.builder</name>
\t\t\t<arguments>
\t\t\t</arguments>
\t\t</buildCommand>
\t\t<buildCommand>
\t\t\t<name>org.eclipse.wst.validation.validationbuilder</name>
\t\t\t<arguments>
\t\t\t</arguments>
\t\t</buildCommand>
\t</buildSpec>
\t<natures>
\t\t<nature>org.eclipse.jem.workbench.JavaEMFNature</nature>
\t\t<nature>org.eclipse.wst.common.modulecore.ModuleCoreNature</nature>
\t\t<nature>org.eclipse.wst.common.project.facet.core.nature</nature>
\t\t<nature>com.workday.wtp.ws.cloud.assembly.nature</nature>
\t\t<nature>org.eclipse.jdt.core.javanature</nature>
\t\t<nature>com.capeclear.wtp.facet.assembly.nature</nature>
\t</natures>
</projectDescription>
""".encode("utf-8")


def _cc_facet_assembly_xml() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<model modelId="com.capeclear.wtp.facet.assembly.facet.AssemblyFacetInstallDataModelProvider">
    <map key="IAssemblyFacetInstallDataModelProperties.LINK_URI_LIST"/>
    <list key="ICcFacetInstallDataModelProperties.EXCLUDE_FROM_DEPLOY_SRC"/>
    <value class="java.lang.Boolean" key="ICcFacetInstallDataModelProperties.MARK_GENERATED_DERIVED">true</value>
    <value class="java.lang.Boolean" key="ICcFacetInstallDataModelProperties.USE_CLASSPATH_DEPENDENCY_FOR_PARENT_SERVICE">true</value>
    <value class="java.lang.String" key="ICcFacetInstallDataModelProperties.WS_FOLDER">ws</value>
    <value class="java.lang.Boolean" key="ICcFacetInstallDataModelProperties.COPY_WSDL_FILES_ON_DEPLOY">true</value>
    <value class="java.lang.String" key="IAssemblyFacetInstallDataModelProperties.ASSEMBLY_TEMPLATE_ID">assembly</value>
    <value class="java.lang.Boolean" key="ICcFacetInstallDataModelProperties.EXPORT_REFERENCED_WEBSERVICE_PROJECT_CLASSPATH">false</value>
</model>
"""


def _cc_ws_cloud_assembly_xml(name: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<model modelId="com.workday.wtp.ws.cloud.assembly.facet.WsCloudAssemblyFacetInstallDataModelProvider">
    <value class="java.lang.String" key="ICcFacetInstallDataModelProperties.MODULE_SERVICE_TOKENIZED_NAME">@PROJECT_NAME@</value>
    <list key="ICcFacetInstallDataModelProperties.EXCLUDE_FROM_DEPLOY_SRC"/>
    <value class="java.lang.String" key="IWsCloudAssemblyFacetInstallDataModelProperties.WD_INTEGRATION_TYPE">regular.e2</value>
    <value class="java.lang.Boolean" key="ICcFacetInstallDataModelProperties.MARK_GENERATED_DERIVED">true</value>
    <value class="java.lang.Boolean" key="ICcFacetInstallDataModelProperties.MODULE_SERVICE_NAME_PROJECT">true</value>
    <value class="java.lang.Boolean" key="ICcFacetInstallDataModelProperties.USE_CLASSPATH_DEPENDENCY_FOR_PARENT_SERVICE">true</value>
    <value class="java.lang.String" key="ICcFacetInstallDataModelProperties.MODULE_SERVICE_NAME"/>
    <value class="java.lang.String" key="ICcFacetInstallDataModelProperties.WS_FOLDER">ws</value>
    <value class="java.lang.Boolean" key="ICcFacetInstallDataModelProperties.COPY_WSDL_FILES_ON_DEPLOY">true</value>
    <value class="java.lang.Boolean" key="ICcFacetInstallDataModelProperties.MODULE_SERVICE_NAME_CUSTOM">false</value>
    <list key="IWsCloudAssemblyFacetInstallDataModelProperties.MEMBER_OF_CLOUD_COLLECTIONS">
        <value class="java.lang.String">{_esc(name)}</value>
    </list>
    <value class="java.lang.Boolean" key="ICcFacetInstallDataModelProperties.MODULE_SERVICE_NAME_VERSION">false</value>
    <value class="java.lang.Boolean" key="ICcFacetInstallDataModelProperties.EXPORT_REFERENCED_WEBSERVICE_PROJECT_CLASSPATH">false</value>
</model>
""".encode("utf-8")


def _wst_component_xml(name: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?><project-modules id="moduleCoreId" project-version="1.5.0">
    <wb-module deploy-name="{_esc(name)}">
        <wb-resource deploy-path="/" source-path="/ws"/>
    </wb-module>
</project-modules>
""".encode("utf-8")


def _facet_core_xml() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<faceted-project>
  <runtime name="Workday Runtime"/>
  <installed facet="cc.ws.cloud.assembly" version="1.0"/>
  <installed facet="java" version="1.8"/>
  <installed facet="cc.facet.assembly" version="1.0"/>
</faceted-project>
"""


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _esc(value: str) -> str:
    """Escape a string for safe inclusion in XML attribute/text values."""
    return (
        value.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&apos;")
    )


def _prop_key(name: str) -> str:
    """Convert a launch param name to a safe property key, e.g. 'Effective Date' → 'effective.date'."""
    return name.lower().replace(" ", ".")

from lxml import etree as ET
from typing import Any

OAI = 'http://www.openarchives.org/OAI/2.0/'
DATACITE_4 = 'http://datacite.org/schema/kernel-4'
DATACITE_4_2 = 'http://schema.datacite.org/meta/kernel-4.2'
DATACITE_3 = 'http://datacite.org/schema/kernel-3'

KNOWN_DATACITE_NS = {DATACITE_3, DATACITE_4, DATACITE_4_2}

XSLT_NS = b'''<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

    <!-- Identity transform -->
    <xsl:template match="@*|node()">
        <xsl:copy>
            <xsl:apply-templates select="@*|node()"/>
        </xsl:copy>
    </xsl:template>

    <!-- Re-home any descendant of 'resource' whose namespace differs
         from resource's own namespace, into resource's namespace.
         Only applies when resource itself is not in the OAI namespace
         (to avoid mangling HAL-style records where resource has no datacite ns) -->
    <xsl:template match="*[
        ancestor::*[local-name()='resource'] and
        namespace-uri() != namespace-uri(ancestor::*[local-name()='resource']) and
        namespace-uri(ancestor::*[local-name()='resource']) != 'http://www.openarchives.org/OAI/2.0/'
    ]">
        <xsl:element
            name="{local-name()}"
            namespace="{namespace-uri(ancestor::*[local-name()='resource'])}">
            <xsl:apply-templates select="@*|node()"/>
        </xsl:element>
    </xsl:template>

    <!-- Drop xmlns="" attributes -->
    <xsl:template match="@xmlns"/>

</xsl:stylesheet>

    '''

_XSLT_TRANSFORM = ET.XSLT(ET.fromstring(XSLT_NS))

def detect_metadata_namespace(root: ET._Element) -> str | None:
    """Extract the namespace of the resource element inside OAI metadata."""
    resource = root.find('.//{*}resource')
    if resource is None:
        return None
    return resource.nsmap.get(resource.prefix)

def detect_payload_namespace(root: ET._Element) -> str | None:
    """Extract the namespace of the resource element inside OAI metadata."""
    resource = root.find('.//{*}payload')
    if resource is None:
        return None
    return resource.nsmap.get(resource.prefix)

def preprocess_xml(root: ET._Element) -> str:
    result = _XSLT_TRANSFORM(root)
    return ET.tostring(result, encoding='unicode')


def get_resource(metadata: dict[str, Any], metadata_namespace: str | None, payload_ns: str | None) -> tuple[dict[str, Any], str] | None:
    if metadata_namespace is not None and metadata_namespace.rstrip('/') in KNOWN_DATACITE_NS:
        if payload_ns is not None:
            oai_wrapper = f'{payload_ns}:oai_datacite'
            oai_payload = f'{payload_ns}:payload'

            metadata = metadata[oai_wrapper][oai_payload]

        resource = metadata[f'{metadata_namespace}:resource']
        return resource, metadata_namespace
    elif metadata_namespace is not None:
        # e.g. HAL or other known formats
        resource = metadata[f'{metadata_namespace}:resource']
        return resource, DATACITE_4
    return None

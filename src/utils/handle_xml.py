from lxml import etree as ET

OAI = 'http://www.openarchives.org/OAI/2.0/'
DATACITE_4 = 'http://datacite.org/schema/kernel-4'
DATACITE_3 = 'http://datacite.org/schema/kernel-3/'

OAI_WRAPPER = 'http://schema.datacite.org/oai/oai-1.1/:oai_datacite'
OAI_PAYLOAD = 'http://schema.datacite.org/oai/oai-1.1/:payload'

KNOWN_DATACITE_NS = {DATACITE_3, DATACITE_4}

def detect_metadata_namespace(root: ET._Element) -> str | None:
    """Extract the namespace of the resource element inside OAI metadata."""
    resource = root.find('.//{*}resource')
    if resource is None:
        return None
    return resource.nsmap.get(resource.prefix)

def preprocess_xml(root: ET._Element) -> str:
    xslt_transform = b'''<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

    <!-- Identity transform -->
    <xsl:template match="@*|node()">
        <xsl:copy>
            <xsl:apply-templates select="@*|node()"/>
        </xsl:copy>
    </xsl:template>

    <!-- Re-home no-namespace elements that are inside a 'resource' element,
         using whatever namespace 'resource' itself has -->
    <xsl:template match="*[namespace-uri()='' and ancestor::*[local-name()='resource']]">
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

    xslt_tree = ET.fromstring(xslt_transform)
    transform = ET.XSLT(xslt_tree)
    result = transform(root)
    return ET.tostring(result, encoding='unicode')

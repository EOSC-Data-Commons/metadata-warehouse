import unittest

from lxml import etree as ET

from src.utils import handle_xml

DANS_XML = """
    <record xmlns="http://www.openarchives.org/OAI/2.0/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <header>
    <identifier>doi:10.34894/CKRZPV</identifier>
    <datestamp>2025-07-05T00:00:27Z</datestamp>
    <setSpec>Arts_Humanities</setSpec>
    <setSpec>SSH</setSpec>
    <setSpec>dataversenl</setSpec>
    <setSpec>DCCD</setSpec>
  </header>
  <metadata>
    <resource xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://datacite.org/schema/kernel-4" xsi:schemaLocation="http://datacite.org/schema/kernel-4 http://schema.datacite.org/meta/kernel-4.1/metadata.xsd">
    </resource>
   </metadata> 
   </record>
"""

HAL_XML = """
    <record xmlns="http://www.openarchives.org/OAI/2.0/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <header status="">
    <identifier>oai:HAL:hal-03456211v1</identifier>
    <datestamp>2025-06-27</datestamp>
    <setSpec>type:ART</setSpec>
    <setSpec>subject:sdv</setSpec>
    <setSpec>collection:INSERM</setSpec>
    <setSpec>collection:SITE-ALSACE</setSpec>
  </header>
  <metadata xmlns:datacite="http://datacite.org/schema/kernel-4">
    <resource xsi:schemaLocation="http://datacite.org/schema/kernel-4 https://schema.datacite.org/meta/kernel-4.4/metadata.xsd">
    </resource>
    </metadata>
    </record>
"""

ONEDATA_XML = """
    <record xmlns="http://www.openarchives.org/OAI/2.0/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" >
    <header>
        <identifier>oai:demo.onedata.org:2fd07bf5f3314cd9ce4c574342ddca86ch0dd1</identifier>
        <datestamp>2025-07-21T13:41:09Z</datestamp>
        <setSpec>70106c451c719edc26ddaf19be9f1609ch6e74</setSpec>
    </header>
    <metadata>
        <oai_datacite xmlns="http://schema.datacite.org/oai/oai-1.1/"
                      xsi:schemaLocation="http://schema.datacite.org/oai/oai-1.1/ http://schema.datacite.org/oai/oai-1.1/oai.xsd">
            <schemaVersion>4</schemaVersion>
            <datacentreSymbol>demo.onedata.org</datacentreSymbol>
            <payload>
                <resource xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                          xmlns="http://datacite.org/schema/kernel-4"
                          xsi:schemaLocation="http://datacite.org/schema/kernel-4 https://schema.datacite.org/meta/kernel-4/metadata.xsd">
                    
                </resource>
            </payload>
        </oai_datacite>
    </metadata>
</record>
            
"""

HZDR_XML = """
    <record xmlns="http://www.openarchives.org/OAI/2.0/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <header>
    <identifier>oai:rodare.hzdr.de:2082</identifier>
    <datestamp>2024-08-12T09:47:59Z</datestamp>
    <setSpec>openaire_data</setSpec>
    <setSpec>user-rodare</setSpec>
    <setSpec>user-fwi</setSpec>
    <setSpec>user-ibc</setSpec>
  </header>
  <metadata>
    <oai_datacite xmlns="http://schema.datacite.org/oai/oai-1.0/" xsi:schemaLocation="http://schema.datacite.org/oai/oai-1.0/ oai_datacite.xsd">
      <isReferenceQuality>true</isReferenceQuality>
      <schemaVersion>4.1</schemaVersion>
      <datacentreSymbol>CERN.ZENODO</datacentreSymbol>
      <payload>
        <resource xmlns="http://datacite.org/schema/kernel-4" xsi:schemaLocation="http://datacite.org/schema/kernel-4 http://schema.datacite.org/meta/kernel-4.1/metadata.xsd">
        </resource>
        </payload>
        </oai_datacite>
        </metadata>
        </record>    
"""


class TestHandleXml(unittest.TestCase):
    def test_detect_metadata_namespace_DANS(self):
        root = ET.fromstring(DANS_XML)

        meta_ns = handle_xml.detect_metadata_namespace(root)
        payload_ns = handle_xml.detect_payload_namespace(root)

        self.assertEqual(meta_ns, 'http://datacite.org/schema/kernel-4')
        self.assertEqual(payload_ns, None)

    def test_detect_metadata_namespace_HAL(self):
        root = ET.fromstring(HAL_XML)

        meta_ns = handle_xml.detect_metadata_namespace(root)
        payload_ns = handle_xml.detect_payload_namespace(root)

        self.assertEqual(meta_ns, 'http://www.openarchives.org/OAI/2.0/')
        self.assertEqual(payload_ns, None)

    def test_detect_metadata_namespace_ONEDATA(self):
        root = ET.fromstring(ONEDATA_XML)

        meta_ns = handle_xml.detect_metadata_namespace(root)
        payload_ns = handle_xml.detect_payload_namespace(root)

        self.assertEqual(meta_ns, 'http://datacite.org/schema/kernel-4')
        self.assertEqual(payload_ns, 'http://schema.datacite.org/oai/oai-1.1/')

    def test_detect_metadata_namespace_HZDR(self):
        root = ET.fromstring(HZDR_XML)

        meta_ns = handle_xml.detect_metadata_namespace(root)
        payload_ns = handle_xml.detect_payload_namespace(root)

        self.assertEqual(meta_ns, 'http://datacite.org/schema/kernel-4')
        self.assertEqual(payload_ns, 'http://schema.datacite.org/oai/oai-1.0/')

import unittest

from huashi.runninghub_inspector import extract_webapp_id, inspect_runninghub_source, parse_runninghub_text


class RunningHubInspectorTest(unittest.TestCase):
    def test_extract_webapp_id_from_runninghub_urls(self):
        self.assertEqual(
            extract_webapp_id("https://www.runninghub.cn/call-api/api-detail/2014608238859259906?apiType=4"),
            "2014608238859259906",
        )
        self.assertEqual(
            extract_webapp_id("https://www.runninghub.cn/ai-detail/2054095300863774721"),
            "2054095300863774721",
        )

    def test_parse_node_info_list_from_json_sample(self):
        result = parse_runninghub_text(
            """
            {
              "webappName": "照片卡通化",
              "description": "<p>一键转换</p>",
              "webappId": "123456",
              "nodeInfoList": [
                {"nodeId": "3", "fieldName": "image", "fieldValue": "input.png"},
                {"nodeId": "7", "fieldName": "prompt", "fieldValue": "cartoon"}
              ]
            }
            """
        )

        self.assertEqual(result.webapp_id, "123456")
        self.assertEqual(result.app_name, "照片卡通化")
        self.assertEqual(result.description, "一键转换")
        self.assertEqual(result.node_id, "3")
        self.assertEqual(result.field_name, "image")
        self.assertEqual(result.prompt_node_id, "7")
        self.assertEqual(result.prompt_field_name, "prompt")
        self.assertEqual(result.inputs[0]["type"], "image")

    def test_parse_api_call_demo_payload(self):
        result = parse_runninghub_text(
            """
            {
              "webappName": "3D微缩模型转换器",
              "nodeInfoList": [
                {"nodeId": "191", "nodeName": "LoadImage", "fieldName": "image", "fieldType": "IMAGE", "fieldValue": "demo.jpg"}
              ]
            }
            """,
            webapp_id="2054095300863774721",
        )

        self.assertEqual(result.webapp_id, "2054095300863774721")
        self.assertEqual(result.app_name, "3D微缩模型转换器")
        self.assertEqual(result.node_id, "191")
        self.assertEqual(result.field_name, "image")
        self.assertEqual(result.output_type, "png")

    def test_parse_text_and_select_inputs(self):
        result = parse_runninghub_text(
            """
            {
              "nodeInfoList": [
                {"nodeId": "20", "fieldName": "default_value", "fieldValue": "杭州", "fieldType": "STRING", "description": "国家/城市名", "fieldData": "[\\"STRING\\", {\\"default\\": \\"\\", \\"multiline\\": true}]"},
                {"nodeId": "2", "fieldName": "aspectRatio", "fieldValue": "1:1", "fieldType": "LIST", "description": "图像比例", "fieldData": "[[\\"auto\\", \\"1:1\\", \\"4:3\\"], {\\"default\\": \\"4:3\\"}]"}
              ]
            }
            """
        )

        self.assertEqual(result.node_id, "20")
        self.assertEqual(result.field_name, "default_value")
        self.assertEqual(result.inputs[0]["type"], "textarea")
        self.assertEqual(result.inputs[0]["label"], "国家/城市名")
        self.assertEqual(result.inputs[1]["type"], "select")
        self.assertEqual(result.inputs[1]["options"], ["auto", "1:1", "4:3"])

    def test_inspect_uses_sample_as_private_page_fallback(self):
        result = inspect_runninghub_source(
            "https://www.runninghub.cn/ai-detail/123456",
            '{"nodeInfoList": [{"nodeId": "191", "fieldName": "image", "fieldValue": "a.png"}]}',
        )

        self.assertEqual(result["webapp_id"], "123456")
        self.assertEqual(result["node_id"], "191")
        self.assertEqual(result["field_name"], "image")


if __name__ == "__main__":
    unittest.main()

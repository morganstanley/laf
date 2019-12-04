"""
Factory module to create
mime type
"""

import json
import yaml


class TypesObj():
    """
    Factory class for mime types
    """
    @staticmethod
    def factory(mime_type):
        """
        Create json or yaml object
        """
        if mime_type == 'application/json':
            return JsonObj()
        if mime_type == 'application/yaml':
            return YamlObj()
        return None


class JsonObj():
    """
    JSON object
    """
    def encode(self, msg):
        """
        json data encode
        """
        return json.dumps(msg)

    def decode(self, msg):
        """
        json data decode
        """
        return json.loads(msg.decode())


class YamlObj():
    """
    YAML object
    """
    def encode(self, msg):
        """
        yaml data encode
        """
        return yaml.dump(msg)

    def decode(self, msg):
        """
        yaml data decode
        """
        return yaml.load(msg)

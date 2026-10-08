from pathlib import Path
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory, json_format


class Contracts:
    def __init__(self, path):
        self.pool = descriptor_pool.DescriptorPool()
        self.files = descriptor_pb2.FileDescriptorSet.FromString(Path(path).read_bytes()).file
        pending = list(self.files)
        while pending:
            progress = False
            for file in list(pending):
                try:
                    self.pool.Add(file)
                except TypeError:
                    continue
                pending.remove(file)
                progress = True
            if not progress:
                raise ValueError("Unresolved protobuf dependencies")

    def cls(self, name):
        return message_factory.GetMessageClass(self.pool.FindMessageTypeByName(name))

    def new(self, name, **fields):
        return self.cls(name)(**fields)

    def parse(self, name, data):
        return self.cls(name).FromString(data)

    def json(self, message):
        return json_format.MessageToDict(message, preserving_proto_field_name=True)

    def describe(self, wrapper):
        result=self.json(wrapper)
        try:
            result['payload']=self.json(self.parse(wrapper.message_type_name,wrapper.message_data))
            result['schema_source']='installed_client_descriptor'
        except Exception as exc:
            result['payload_error']=str(exc)
        return result

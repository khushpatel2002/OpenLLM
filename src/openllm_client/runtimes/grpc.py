# Copyright 2023 BentoML Team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import asyncio
import logging
import typing as t

import orjson

import openllm

from .base import BaseAsyncClient, BaseClient

if t.TYPE_CHECKING:
    import grpc_health.v1.health_pb2 as health_pb2
    from bentoml.grpc.v1.service_pb2 import Response

logger = logging.getLogger(__name__)


class GrpcClientMixin:
    _metadata: Response

    @property
    def model_name(self) -> str:
        try:
            return self._metadata.json.struct_value.fields["model_name"].string_value
        except KeyError:
            raise RuntimeError("Malformed service endpoint. (Possible malicious)")

    @property
    def framework(self) -> t.Literal["pt", "flax", "tf"]:
        try:
            value = self._metadata.json.struct_value.fields["framework"].string_value
            if value not in ("pt", "flax", "tf"):
                raise KeyError
            return value
        except KeyError:
            raise RuntimeError("Malformed service endpoint. (Possible malicious)")

    @property
    def timeout(self) -> int:
        try:
            return int(self._metadata.json.struct_value.fields["timeout"].number_value)
        except KeyError:
            raise RuntimeError("Malformed service endpoint. (Possible malicious)")

    @property
    def model_id(self) -> str:
        try:
            return self._metadata.json.struct_value.fields["model_id"].string_value
        except KeyError:
            raise RuntimeError("Malformed service endpoint. (Possible malicious)")

    @property
    def configuration(self) -> dict[str, t.Any]:
        try:
            v = self._metadata.json.struct_value.fields["configuration"].string_value
            return orjson.loads(v)
        except KeyError:
            raise RuntimeError("Malformed service endpoint. (Possible malicious)")

    def postprocess(self, result: Response) -> openllm.GenerationOutput:
        from google.protobuf.json_format import MessageToDict

        return openllm.GenerationOutput(**MessageToDict(result.json, preserving_proto_field_name=True))


class GrpcClient(GrpcClientMixin, BaseClient, client_type="grpc"):
    def __init__(self, address: str, timeout: int = 30):
        self._host, self._port = address.split(":")
        super().__init__(address, timeout)

    def health(self) -> health_pb2.HealthCheckResponse:
        return asyncio.run(self._cached.health("bentoml.grpc.v1.BentoService"))


class AsyncGrpcClient(GrpcClientMixin, BaseAsyncClient, client_type="grpc"):
    def __init__(self, address: str, timeout: int = 30):
        self._host, self._port = address.split(":")
        super().__init__(address, timeout)

    async def health(self) -> health_pb2.HealthCheckResponse:
        return await self._cached.health("bentoml.grpc.v1.BentoService")

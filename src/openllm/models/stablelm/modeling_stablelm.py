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

import logging
import typing as t

from transformers import StoppingCriteria, StoppingCriteriaList

import openllm

from ..._prompt import default_formatter
from .configuration_stablelm import DEFAULT_PROMPT_TEMPLATE, SYSTEM_PROMPT

if t.TYPE_CHECKING:
    import transformers  # noqa


class StopOnTokens(StoppingCriteria):
    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor, **kwargs) -> bool:
        stop_ids = set([50278, 50279, 50277, 1, 0])
        return input_ids[0][-1] in stop_ids


if t.TYPE_CHECKING:
    import torch
else:
    torch = openllm.utils.LazyLoader("torch", globals(), "torch")


logger = logging.getLogger(__name__)


class StableLM(openllm.LLM["transformers.GPTNeoXForCausalLM", "transformers.GPTNeoXTokenizerFast"]):
    __openllm_internal__ = True

    def llm_post_init(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.load_in_mha = True if not torch.cuda.is_available() else False

    @property
    def import_kwargs(self):
        model_kwds = {
            "torch_dtype": torch.float16 if torch.cuda.is_available() else torch.float32,
            "load_in_8bit": False,
            "device_map": "auto" if torch.cuda.is_available() and torch.cuda.device_count() > 1 else None,
        }
        tokenizer_kwds: dict[str, t.Any] = {}
        return model_kwds, tokenizer_kwds

    def sanitize_parameters(
        self,
        prompt: str,
        temperature: float | None = None,
        max_new_tokens: int | None = None,
        top_k: int | None = None,
        top_p: float | None = None,
        use_default_prompt_template: bool = False,
        **attrs: t.Any,
    ) -> tuple[str, dict[str, t.Any], dict[str, t.Any]]:
        if "tuned" in self._model_id and use_default_prompt_template:
            prompt_variables = {
                k: v
                for k, v in attrs.items()
                if k in default_formatter.extract_template_variables(DEFAULT_PROMPT_TEMPLATE)
            }
            if "instruction" in prompt_variables:
                raise RuntimeError(
                    "'instruction' should be passed as the first argument "
                    "instead of kwargs when 'use_default_prompt_template=True'"
                )
            system_prompt = prompt_variables.pop("system_prompt", SYSTEM_PROMPT)
            prompt_text = DEFAULT_PROMPT_TEMPLATE.format(instruction=prompt, system_prompt=system_prompt)
        else:
            prompt_text = prompt

        generation_config = {
            "max_new_tokens": max_new_tokens,
            "temperature": temperature,
            "top_k": top_k,
            "top_p": top_p,
        }

        return prompt_text, generation_config, {}

    def postprocess_generate(self, prompt: str, generation_result: list[str], **_: t.Any) -> str:
        return generation_result[0]

    def generate(self, prompt: str, **attrs: t.Any) -> list[str]:
        generation_kwargs = {
            "do_sample": True,
            "generation_config": self.config.model_construct_env(**attrs).to_generation_config(),
            "pad_token_id": self.tokenizer.eos_token_id,
            "stopping_criteria": StoppingCriteriaList([StopOnTokens()]),
        }

        if torch.cuda.is_available():
            self.model.cuda()

        inputs = t.cast("torch.Tensor", self.tokenizer(prompt, return_tensors="pt")).to(self.device)
        tokens = self.model.generate(**inputs, **generation_kwargs)
        return [self.tokenizer.decode(tokens[0], skip_special_tokens=True)]

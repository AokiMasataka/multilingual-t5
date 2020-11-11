# Copyright 2020 The mT5 Authors.
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

"""Add Tasks to registry."""
import functools

from multilingual_t5 import preprocessors
from multilingual_t5 import utils

import t5.data
from t5.data import sentencepiece_vocabulary
from t5.evaluation import metrics
import tensorflow_datasets as tfds

DEFAULT_SPM_PATH = "gs://t5-data/vocabs/mc4.250000.100extra/sentencepiece.model"


DEFAULT_TEMPERATURE = 1.0 / 0.3
DEFAULT_MIX_RATE = functools.partial(
    t5.data.utils.rate_num_examples, temperature=DEFAULT_TEMPERATURE)

DEFAULT_VOCAB = sentencepiece_vocabulary.SentencePieceVocabulary(
    DEFAULT_SPM_PATH)
DEFAULT_OUTPUT_FEATURES = {
    "inputs": t5.data.Feature(
        vocabulary=DEFAULT_VOCAB, add_eos=True, required=False),
    "targets": t5.data.Feature(
        vocabulary=DEFAULT_VOCAB, add_eos=True)
}

MC4_LANGS = tfds.text.c4.MC4_LANGUAGES

# Multilingual BERT was trained on 104 languages. We include 103 of these
# languages, as tfds.wikipedia doesn't distinguish between simplified and
# traditional Chinese, and only contains "zh" (which is a mix of simplified
# and traditional).
# https://github.com/google-research/bert/blob/master/multilingual.md
WIKI_LANGS = [
    "af", "an", "ar", "ast", "az", "azb", "ba", "bar", "be", "bg", "bn", "bpy",
    "br", "bs", "ca", "ce", "ceb", "cs", "cv", "cy", "da", "de", "el", "en",
    "es", "et", "eu", "fa", "fi", "fr", "fy", "ga", "gl", "gu", "he", "hi",
    "hr", "ht", "hu", "hy", "id", "io", "is", "it", "ja", "jv", "ka", "kk",
    "kn", "ko", "ky", "la", "lb", "lmo", "lt", "lv", "mg", "min", "mk", "ml",
    "mn", "mr", "ms", "my", "nds-nl", "ne", "new", "nl", "nn", "no", "oc",
    "pa", "pl", "pms", "pnb", "pt", "ro", "ru", "scn", "sco", "sh", "sk", "sl",
    "sq", "sr", "su", "sv", "sw", "ta", "te", "tg", "th", "tl", "tr", "tt",
    "uk", "ur", "uz", "vi", "vo", "war", "yo", "zh"
]

# =========================== Pretraining Tasks/Mixtures =======================

# mC4
for lang in MC4_LANGS:
  t5.data.TaskRegistry.add(
      "mc4.{}".format(lang.replace("-", "_")),
      t5.data.TfdsTask,
      tfds_name="c4/multilingual:3.0.1",
      splits={"train": lang,
              "validation": f"{lang}-validation"},
      text_preprocessor=functools.partial(
          t5.data.preprocessors.rekey,
          key_map={"inputs": None, "targets": "text"}),
      token_preprocessor=t5.data.preprocessors.span_corruption,
      output_features=DEFAULT_OUTPUT_FEATURES,
      metric_fns=[])

mc4 = ["mc4.{}".format(lang.replace("-", "_")) for lang in MC4_LANGS]
t5.data.MixtureRegistry.add("mc4", mc4, default_rate=DEFAULT_MIX_RATE)

# Wikipedia
for lang in WIKI_LANGS:
  t5.data.TaskRegistry.add(
      "wiki.{}".format(lang.replace("-", "_")),
      t5.data.TfdsTask,
      tfds_name="wikipedia/20200301.{}:1.0.0".format(lang),
      text_preprocessor=[
          functools.partial(
              t5.data.preprocessors.rekey,
              key_map={
                  "inputs": None,
                  "targets": "text"
              }),
      ],
      token_preprocessor=t5.data.preprocessors.span_corruption,
      output_features=DEFAULT_OUTPUT_FEATURES,
      metric_fns=[])

wiki = ["wiki.{}".format(lang.replace("-", "_")) for lang in WIKI_LANGS]
t5.data.MixtureRegistry.add("wiki", wiki, default_rate=DEFAULT_MIX_RATE)

# Mixture of mC4 and WIKI
t5.data.MixtureRegistry.add(
    "mc4_wiki", mc4 + wiki, default_rate=DEFAULT_MIX_RATE)

# =========================== Fine-tuning Tasks/Mixtures =======================
# ----- XNLI -----
# XNLI zero-shot task. This fine-tunes on English MNLI training data and then
# evaluates on multilingual XNLI dev/test data.

XNLI_LANGS = [
    "ar", "bg", "de", "el", "en", "es", "fr", "hi", "ru", "sw", "th", "tr",
    "ur", "vi", "zh"
]

t5.data.TaskRegistry.add(
    "xnli_train",
    t5.data.TfdsTask,
    tfds_name="multi_nli/plain_text:1.0.0",
    splits=["train"],
    text_preprocessor=preprocessors.process_mnli,
    output_features=DEFAULT_OUTPUT_FEATURES,
    metric_fns=[metrics.accuracy])
for lang in XNLI_LANGS:
  t5.data.TaskRegistry.add(
      "xnli_dev_test.{}".format(lang),
      t5.data.TfdsTask,
      tfds_name="xnli:1.1.0",
      splits=["validation", "test"],
      text_preprocessor=[
          functools.partial(
              preprocessors.process_xnli, target_languages=[lang])
      ],
      output_features=DEFAULT_OUTPUT_FEATURES,
      metric_fns=[metrics.accuracy])
t5.data.TaskRegistry.add(
    "xnli_dev_test.all_langs",
    t5.data.TfdsTask,
    tfds_name="xnli:1.1.0",
    splits=["validation", "test"],
    text_preprocessor=[
        functools.partial(
            preprocessors.process_xnli, target_languages=XNLI_LANGS)
    ],
    output_features=DEFAULT_OUTPUT_FEATURES,
    metric_fns=[metrics.accuracy])
xnli_zeroshot = (["xnli_train", "xnli_dev_test.all_langs"] + \
                  ["xnli_dev_test.{}".format(lang) for lang in XNLI_LANGS])
t5.data.MixtureRegistry.add("xnli_zeroshot", xnli_zeroshot, default_rate=1.0)

# ----- PAWS -----
label_names = ["different_meaning", "paraphrase"]
text_preprocessor = [
    functools.partial(
        t5.data.preprocessors.glue,
        benchmark_name="paws",
        label_names=label_names,
        feature_names=["sentence1", "sentence2"],
        id_key=None)
]

postprocess_fn = functools.partial(
        t5.data.postprocessors.string_label_to_class_id,
        label_classes=label_names)

t5.data.TaskRegistry.add(
    "paws",
    t5.data.TfdsTask,
    tfds_name="paws_x_wiki/en:1.0.0",
    splits=["train"],
    text_preprocessor=text_preprocessor,
    output_features=DEFAULT_OUTPUT_FEATURES,
    postprocess_fn=postprocess_fn,
    metric_fns=[metrics.accuracy])

for lang in utils.PAWSX_LANGS:
  t5.data.TaskRegistry.add(
      "pawsx_dev_test.{}".format(lang),
      t5.data.TfdsTask,
      tfds_name="paws_x_wiki/{}:1.0.0".format(lang),
      splits=["validation", "test"],
      text_preprocessor=text_preprocessor,
      output_features=DEFAULT_OUTPUT_FEATURES,
      postprocess_fn=postprocess_fn,
      metric_fns=[metrics.accuracy])

  t5.data.TaskRegistry.add(
      "pawsx_translate.{}".format(lang),
      t5.data.TfdsTask,
      tfds_name="paws_x_wiki/{}:1.0.0".format(lang),
      splits=["train"],
      text_preprocessor=text_preprocessor,
      output_features=DEFAULT_OUTPUT_FEATURES,
      postprocess_fn=postprocess_fn,
      metric_fns=[metrics.accuracy])

t5.data.TaskRegistry.add(
    "pawsx_dev_test.all_langs",
    splits=["validation", "test"],
    dataset_fn=utils.pawsx_all_langs_dataset_fn,
    text_preprocessor=text_preprocessor,
    output_features=DEFAULT_OUTPUT_FEATURES,
    postprocess_fn=postprocess_fn,
    metric_fns=[metrics.accuracy])

# PAWSX Zero-Shot
pawsx = ["paws"] + ["pawsx_dev_test.all_langs"] + [
    "pawsx_dev_test.{}".format(lang) for lang in utils.PAWSX_LANGS
]
t5.data.MixtureRegistry.add("pawsx_zeroshot", pawsx, default_rate=1.0)

pawsx_translate = [
    "pawsx_translate.{}".format(lang) for lang in utils.PAWSX_LANGS
] + ["pawsx_dev_test.all_langs"
    ] + ["pawsx_dev_test.{}".format(lang) for lang in utils.PAWSX_LANGS]
t5.data.MixtureRegistry.add(
    "pawsx_translate", pawsx_translate, default_rate=1.0)

# ----- TyDiQA GoldP-----
# The "validation" split contains all the validation examples for all the
# individual languages together.
TYDIQA_LANGS = ["ar", "bn", "en", "fi", "id", "ko", "ru", "sw", "te"]
t5.data.TaskRegistry.add(
    "tydiqa_train_dev",
    t5.data.TfdsTask,
    tfds_name="tydi_qa/goldp:2.0.0",
    splits=["train", "validation"],
    text_preprocessor=preprocessors.xquad,
    postprocess_fn=t5.data.postprocessors.qa,
    output_features=DEFAULT_OUTPUT_FEATURES,
    metric_fns=[metrics.squad])

for lang in TYDIQA_LANGS:
  t5.data.TaskRegistry.add(
      "tydiqa_dev.{}".format(lang),
      t5.data.TfdsTask,
      tfds_name="tydi_qa/goldp:2.0.0",
      splits={"validation": "validation-{}".format(lang)},
      text_preprocessor=preprocessors.xquad,
      postprocess_fn=t5.data.postprocessors.qa,
      output_features=DEFAULT_OUTPUT_FEATURES,
      metric_fns=[metrics.squad])

tydiqa = (["tydiqa_train_dev"] + \
            ["tydiqa_dev.{}".format(lang) for lang in TYDIQA_LANGS])
t5.data.MixtureRegistry.add("tydiqa", tydiqa, default_rate=1.0)


# ----- English SQUAD -----
t5.data.TaskRegistry.add(
    "squad_train_dev",
    t5.data.TfdsTask,
    tfds_name="squad/v1.1:2.0.0",
    splits=["train", "validation"],
    text_preprocessor=preprocessors.xquad,
    postprocess_fn=t5.data.postprocessors.qa,
    output_features=DEFAULT_OUTPUT_FEATURES,
    metric_fns=[metrics.squad])

# ----- XQuAD -----
for lang in utils.XQUAD_LANGS_TRAIN_DEV:
  t5.data.TaskRegistry.add(
      "xquad_translate_train_dev.{}".format(lang),
      t5.data.TfdsTask,
      tfds_name="xquad/{}:2.0.0".format(lang),
      splits={
          "train": "translate-train",
          "validation": "translate-dev"
      },
      text_preprocessor=preprocessors.xquad,
      postprocess_fn=t5.data.postprocessors.qa,
      output_features=DEFAULT_OUTPUT_FEATURES,
      metric_fns=[metrics.squad])

for lang in utils.XQUAD_LANGS_TEST:
  t5.data.TaskRegistry.add(
      "xquad_test.{}".format(lang),
      t5.data.TfdsTask,
      tfds_name="xquad/{}:2.0.0".format(lang),
      splits=["test"],
      text_preprocessor=preprocessors.xquad,
      postprocess_fn=t5.data.postprocessors.qa,
      output_features=DEFAULT_OUTPUT_FEATURES,
      metric_fns=[metrics.squad])

# Additional test task containing all the languages.
t5.data.TaskRegistry.add(
    "xquad_test.all_langs",
    splits=["test"],
    dataset_fn=utils.xquad_all_langs_dataset_fn,
    text_preprocessor=preprocessors.xquad,
    postprocess_fn=t5.data.postprocessors.qa,
    output_features=DEFAULT_OUTPUT_FEATURES,
    metric_fns=[metrics.squad])

# XQuAD Zero-Shot (SQuAD train, SQuAD dev, XQuAD test).
xquad_test = ["xquad_test.{}".format(lang) for lang in utils.XQUAD_LANGS_TEST]
xquad_zeroshot = ["squad_train_dev", "xquad_test.all_langs"] + xquad_test
t5.data.MixtureRegistry.add("xquad_zeroshot", xquad_zeroshot, default_rate=1.0)

# XQuAD Translate-Train (English SQuAD, XQuAD translate-train,
# XQuAD translate-dev, XQuAD test)
# Note that the QA translate-train baselines from Hu et al (XTREME)
# do not include the English data. However, Fang et al (FILTER) do include
# English data.
xquad_translate_train_dev = [
    "xquad_translate_train_dev.{}".format(lang)
    for lang in utils.XQUAD_LANGS_TRAIN_DEV
] + ["squad_train_dev"]
xquad_translate = (xquad_translate_train_dev + \
                    ["xquad_test.all_langs"] + xquad_test)
t5.data.MixtureRegistry.add(
    "xquad_translate", xquad_translate, default_rate=1.0)

# ******** add *********
from sumeval.metrics.lang.lang_ja import LangJA
from sacrebleu import corpus_bleu, TOKENIZERS

lang_ja = LangJA()
def tokenizer_ja(text):
  words = lang_ja.tokenize_with_preprocess(text)
  return " ".join(words)
TOKENIZERS["ja"] = tokenizer_ja

def bleu(targets, predictions):
  predictions = [tf.compat.as_text(x) for x in predictions]

  if isinstance(targets[0], list):
    targets = [[tf.compat.as_text(x) for x in target] for target in targets]
  else:
    targets = [tf.compat.as_text(x) for x in targets]
    targets = [targets]

  bleu_score = corpus_bleu(predictions, targets,smooth_method="exp", smooth_value=0.0,
                 force=False,lowercase=False,tokenize="ja", use_effective_order=False)
  return {"bleu": bleu_score.score}

snow_tsv_path = {
    "train": "./snow_t15_23_train.tsv",
    "validation": "./snow_t15_23_dev.tsv",
    "test": "./snow_t15_23_test.tsv",
}

t5.data.TaskRegistry.add(
    'snow',
    t5.data.TextLineTask,
    split_to_filepattern=snow_tsv_path,
    text_preprocessor=[
      functools.partial(
          preprocessors.parse_tsv,
          field_names=["inputs", "targets"]),
    ],
    output_features=DEFAULT_OUTPUT_FEATURES,
    metric_fns=[bleu])
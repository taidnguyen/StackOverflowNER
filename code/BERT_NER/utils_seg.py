# coding=utf-8
# Copyright 2018 The Google AI Language Team Authors and The HuggingFace Inc. team.
# Copyright (c) 2018, NVIDIA CORPORATION.  All rights reserved.
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
""" Named entity recognition fine-tuning: utilities to work with CoNLL-2003 task. """


import logging
import os
import json

logger = logging.getLogger(__name__)


class InputExample(object):
    """A single training/test example for token classification."""

    def __init__(self, guid, words, labels):
        """Constructs a InputExample.

        Args:
            guid: Unique id for the example.
            words: list. The words of the sequence.
            labels: (Optional) list. The labels for each word of the sequence. This should be
            specified for train and dev examples, but not for test examples.
        """
        self.guid = guid
        self.words = words
        self.labels = labels


class InputFeatures(object):
    """A single set of features of data."""

    def __init__(self, input_ids, input_mask, freq_ids, md_ids, label_ids, label_ids_ctc, label_ids_md):
        self.input_ids = input_ids
        self.input_freq_ids = freq_ids
        self.input_mask = input_mask
        self.md_ids = md_ids
        self.label_ids = label_ids
        self.label_ids_ctc = label_ids_ctc
        self.label_ids_md = label_ids_md


def read_examples_from_file(data_dir, mode, path=None):
    file_path = os.path.join(data_dir, "{}.txt".format(mode))
    if path!=None:
        file_path = path
    guid_index = 1
    examples = []
    with open(file_path, encoding="utf-8") as f:
        words = []
        labels = []
        for line in f:
            if line.startswith("-DOCSTART-") or line == "" or line == "\n":
                if words:
                    examples.append(InputExample(guid="{}-{}".format(mode, guid_index), words=words, labels=labels))
                    guid_index += 1
                    words = []
                    labels = []
            else:
                splits = line.strip().split("\t")
                words.append(splits[0])
                if len(splits) > 1:
                    labels.append(splits[1:])
                else:
                    # Examples could have no label for mode = "test"
                    labels.append("O")
        if words:
            examples.append(InputExample(guid="{}-{}".format(mode, guid_index), words=words, labels=labels))
    return examples


def convert_examples_to_features(
    examples,
    label_list,
    max_seq_length,
    tokenizer,
    cls_token_at_end=False,
    cls_token="[CLS]",
    cls_token_segment_id=1,
    sep_token="[SEP]",
    sep_token_extra=False,
    pad_on_left=False,
    pad_token=0,
    pad_token_md_id=0,
    pad_token_label_id=-100,
    sequence_a_markdown_id=0,
    mask_padding_with_zero=True,
):
    """ Loads a data file into a list of `InputBatch`s
        `cls_token_at_end` define the location of the CLS token:
            - False (Default, BERT/XLM pattern): [CLS] + A + [SEP] + B + [SEP]
            - True (XLNet/GPT pattern): A + [SEP] + B + [SEP] + [CLS]
        `cls_token_segment_id` define the segment id associated to the CLS token (0 for BERT, 2 for XLNet)
    """

    label_map = {label: i for i, label in enumerate(label_list)}
    word_to_id = json.load(open("word_to_id.json","r"))
    word_id_pad = word_to_id["**PAD**"]

    # print("*********************************")
    # print(label_map)
    # print("*********************************")

    features = []
    for (ex_index, example) in enumerate(examples):
        # if ex_index % 10000 == 0:
        #     logger.info("Writing example %d of %d", ex_index, len(examples))

        tokens = []
        label_ids = []
        label_ids_ctc = []
        label_ids_md = []
        word_freq_ids = []
        for word, label in zip(example.words, example.labels):
            # print("*********************************")
            # print(word)
            # print(label)
            # print("*********************************")
            word_tokens = tokenizer.tokenize(word)

            if word not in word_to_id:
                word_id=word_to_id["**UNK**"]
            else:
                word_id = word_to_id[word]

            # bert-base-multilingual-cased sometimes output "nothing ([]) when calling tokenize with just a space.
            if len(word_tokens) > 0:
                tokens.extend(word_tokens)
                # Use the real label id for the first token of the word, and padding ids for the remaining tokens
                label_ids.extend([label_map[label[0]]] + [pad_token_label_id] * (len(word_tokens) - 1))
                label_ids_ctc.extend([label_map[label[1]]] + [pad_token_label_id] * (len(word_tokens) - 1))
                label_ids_md.extend([label_map[label[2]]] + [pad_token_label_id] * (len(word_tokens) - 1))
                word_freq_ids.append(word_id)

            

        # Account for [CLS] and [SEP] with "- 2" and with "- 3" for RoBERTa.
        special_tokens_count = tokenizer.num_special_tokens_to_add() #num_added_tokens()
        if len(tokens) > max_seq_length - special_tokens_count:
            tokens = tokens[: (max_seq_length - special_tokens_count)]
            label_ids = label_ids[: (max_seq_length - special_tokens_count)]
            label_ids_ctc = label_ids_ctc[: (max_seq_length - special_tokens_count)]
            label_ids_md = label_ids_md[: (max_seq_length - special_tokens_count)]
            word_freq_ids = word_freq_ids[: (max_seq_length - special_tokens_count)]

        # The convention in BERT is:
        # (a) For sequence pairs:
        #  tokens:   [CLS] is this jack ##son ##ville ? [SEP] no it is not . [SEP]
        #  type_ids:   0   0  0    0    0     0       0   0   1  1  1  1   1   1
        # (b) For single sequences:
        #  tokens:   [CLS] the dog is hairy . [SEP]
        #  type_ids:   0   0   0   0  0     0   0
        #
        # Where "type_ids" are used to indicate whether this is the first
        # sequence or the second sequence. The embedding vectors for `type=0` and
        # `type=1` were learned during pre-training and are added to the wordpiece
        # embedding vector (and position vector). This is not *strictly* necessary
        # since the [SEP] token unambiguously separates the sequences, but it makes
        # it easier for the model to learn the concept of sequences.
        #
        # For classification tasks, the first vector (corresponding to [CLS]) is
        # used as as the "sentence vector". Note that this only makes sense because
        # the entire model is fine-tuned.
        tokens += [sep_token]
        word_freq_ids+=[word_id_pad]
        label_ids += [pad_token_label_id]
        label_ids_ctc += [pad_token_label_id]
        label_ids_md += [pad_token_label_id]
        if sep_token_extra:
            # roberta uses an extra separator b/w pairs of sentences
            tokens += [sep_token]
            word_freq_ids+=[word_id_pad]
            label_ids += [pad_token_label_id]
            label_ids_ctc += [pad_token_label_id]
            label_ids_md += [pad_token_label_id]
        md_ids = [sequence_a_markdown_id] * len(tokens)

        if cls_token_at_end:
            tokens += [cls_token]
            word_freq_ids+=[word_id_pad]
            label_ids += [pad_token_label_id]
            label_ids_ctc += [pad_token_label_id]
            label_ids_md += [pad_token_label_id]
            md_ids += [cls_token_segment_id]
        else:
            tokens = [cls_token] + tokens
            word_freq_ids = [word_id_pad] + word_freq_ids 
            label_ids = [pad_token_label_id] + label_ids
            label_ids_ctc = [pad_token_label_id] + label_ids_ctc
            label_ids_md = [pad_token_md_id] + label_ids_md
            md_ids = [cls_token_segment_id] + md_ids

        input_ids = tokenizer.convert_tokens_to_ids(tokens)

        # The mask has 1 for real tokens and 0 for padding tokens. Only real
        # tokens are attended to.
        input_mask = [1 if mask_padding_with_zero else 0] * len(input_ids)

        # Zero-pad up to the sequence length.
        padding_length = max_seq_length - len(input_ids)

        if pad_on_left:
            input_ids = ([pad_token] * padding_length) + input_ids
            input_mask = ([0 if mask_padding_with_zero else 1] * padding_length) + input_mask
            word_freq_ids = ([word_id_pad]* padding_length) + word_freq_ids 
            md_ids = ([pad_token_md_id] * padding_length) + md_ids
            label_ids = ([pad_token_label_id] * padding_length) + label_ids
            label_ids_ctc = ([pad_token_label_id] * padding_length) + label_ids_ctc
            label_ids_md = ([pad_token_label_id] * padding_length) + label_ids_md
        else:
            input_ids += [pad_token] * padding_length
            input_mask += [0 if mask_padding_with_zero else 1] * padding_length
            word_freq_ids += [word_id_pad]* padding_length
            md_ids += [pad_token_md_id] * padding_length
            label_ids += [pad_token_label_id] * padding_length
            label_ids_ctc += [pad_token_label_id] * padding_length
            label_ids_md += [pad_token_label_id] * padding_length


        
        while len(word_freq_ids)!=max_seq_length:
            word_freq_ids.append(word_id_pad)

        # print(len(word_freq_ids), len(input_ids))


        assert len(input_ids) == max_seq_length
        assert len(input_mask) == max_seq_length
        assert len(word_freq_ids) == max_seq_length
        assert len(md_ids) == max_seq_length
        assert len(label_ids) == max_seq_length
        assert len(label_ids_ctc) == max_seq_length
        assert len(label_ids_md) == max_seq_length

        # if ex_index < 5:
        #     logger.info("*** Example ***")
        #     logger.info("guid: %s", example.guid)
        #     logger.info("tokens: %s", " ".join([str(x) for x in tokens]))
        #     logger.info("input_ids: %s", " ".join([str(x) for x in input_ids]))
        #     logger.info("input_mask: %s", " ".join([str(x) for x in input_mask]))
        #     logger.info("md_ids: %s", " ".join([str(x) for x in md_ids]))
        #     logger.info("label_ids: %s", " ".join([str(x) for x in label_ids]))
        #     logger.info("label_ids_ctc: %s", " ".join([str(x) for x in label_ids_ctc]))
        #     logger.info("label_ids_md: %s", " ".join([str(x) for x in label_ids_md]))

        features.append(
            InputFeatures(input_ids=input_ids, input_mask=input_mask, freq_ids=word_freq_ids, md_ids=md_ids, label_ids=label_ids, label_ids_ctc=label_ids_ctc, label_ids_md=label_ids_md)
        )
    return features


def get_labels(path):
    if path:
        with open(path, "r") as f:
            labels = f.read().splitlines()
        if "O" not in labels:
            labels = ["O"] + labels
        labels.append("CTC_PRED:0")
        labels.append("CTC_PRED:1")
        labels.append("md_label:O")
        labels.append("md_label:Name")
        return labels
    else:
        return ["O", "B-MISC", "I-MISC", "B-PER", "I-PER", "B-ORG", "I-ORG", "B-LOC", "I-LOC"]

import re
import csv
from transformers import AdamW, AutoModel, AutoModelForSeq2SeqLM, AutoTokenizer, get_linear_schedule_with_warmup, GPT2Model, GPT2Config, GPT2Tokenizer
import pandas as pd
from tqdm import tqdm
from torch.utils.data import DataLoader, Dataset, RandomSampler, SequentialSampler
import torch.utils.checkpoint as checkpoint
import torch
import numpy as np
import json
from time import time
from random import choice, randint
import math
import functools
print("Importing dependencies: ")
import os
import faiss
import nlp
import ast
import pprint


def make_qa_s2s_model(model_name, from_file=None, device="cuda:0"):
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_name).to(device)
    if from_file is not None:
        # has model weights, optimizer, and scheduler states
        param_dict = torch.load(from_file)
        model.load_state_dict(param_dict["model"])
    return tokenizer, model


# generate answer from input "question: ... context: <p> ..."
def qa_s2s_generate(
    question_doc,
    qa_s2s_model,
    qa_s2s_tokenizer,
    num_answers=1,
    num_beams=None,
    min_len=64,
    max_len=256,
    do_sample=False,
    temp=1.0,
    top_p=None,
    top_k=None,
    max_input_length=512,
    device="cuda:0",
):
    model_inputs = make_qa_s2s_batch(
        [(question_doc, "A")], qa_s2s_tokenizer, max_input_length, device=device,)
    n_beams = num_answers if num_beams is None else max(num_beams, num_answers)
    generated_ids = qa_s2s_model.generate(
        input_ids=model_inputs["input_ids"],
        attention_mask=model_inputs["attention_mask"],
        min_length=min_len,
        max_length=max_len,
        do_sample=do_sample,
        early_stopping=True,
        num_beams=1 if do_sample else n_beams,
        temperature=temp,
        top_k=top_k,
        top_p=top_p,
        eos_token_id=qa_s2s_tokenizer.eos_token_id,
        no_repeat_ngram_size=3,
        num_return_sequences=num_answers,
        decoder_start_token_id=qa_s2s_tokenizer.bos_token_id,
    )
    return [qa_s2s_tokenizer.decode(ans_ids, skip_special_tokens=True).strip() for ans_ids in generated_ids]


def make_qa_s2s_batch(qa_list, tokenizer, max_len=64, max_a_len=360, device="cuda:0"):
    q_ls = [q for q, a in qa_list]
    a_ls = [a for q, a in qa_list]
    q_toks = tokenizer.batch_encode_plus(
        q_ls, max_length=max_len, pad_to_max_length=True)
    q_ids, q_mask = (
        torch.LongTensor(q_toks["input_ids"]).to(device),
        torch.LongTensor(q_toks["attention_mask"]).to(device),
    )
    a_toks = tokenizer.batch_encode_plus(a_ls, max_length=min(
        max_len, max_a_len), pad_to_max_length=True)
    a_ids, a_mask = (
        torch.LongTensor(a_toks["input_ids"]).to(device),
        torch.LongTensor(a_toks["attention_mask"]).to(device),
    )
    lm_labels = a_ids[:, 1:].contiguous().clone()
    lm_labels[a_mask[:, 1:].contiguous() == 0] = -100
    model_inputs = {
        "input_ids": q_ids,
        "attention_mask": q_mask,
        "decoder_input_ids": a_ids[:, :-1].contiguous(),
        "lm_labels": lm_labels,
    }
    return model_inputs


qa_s2s_tokenizer = AutoTokenizer.from_pretrained('yjernite/bart_eli5')
qa_s2s_model = AutoModelForSeq2SeqLM.from_pretrained('yjernite/bart_eli5').to('cuda:1')
_ = qa_s2s_model.eval()


# qa_s2s_tokenizer, pre_model = make_qa_s2s_model(
#     model_name="yjernite/bart_eli5",
#     from_file="msmarco_bart_wellformedans_0.pth",
#     device="cuda:1"
# )
# qa_s2s_model = torch.nn.DataParallel(pre_model)
# _ = qa_s2s_model.eval()
# question = "Who is Iron Man?"
# doc = "Iron man is a Marvel comic book character who is one of the most popular superheroes."
#

#
# question = "What is a cloud?"
#
# # concatenate question and support document into BART input
# question_doc = "question: {} context: {}".format(question, doc)

# question_doc = "question: Who is iron man? context: \<P> Tony Stark"

question_doc = "question: Why does water heated to room temperature feel colder than the air around it? context: \<P> when the skin is completely wet. The body continuously loses ... this heat comes from the liquid itself and the surrounding gas and surfaces. \<P> protected by a glass panel. Consequently, these types of collectors... Since heat loss due to convection cannot cross a vacuum, it forms an efficient isolation mechanism to keep heat inside the collector pipes. Since two flat \<P> ... \<P> changes. Conduction On... Fluids—especially gases—are less conductive. Thermal contact conductance is the study of heat conduction between solid bodies in contact. The process of heat transfer"


# generate an answer with beam search
answer = qa_s2s_generate(
        question_doc, qa_s2s_model, qa_s2s_tokenizer,
        num_answers=1,
        num_beams=8,
        min_len=64,
        max_len=256,
        max_input_length=1024,
        device="cuda:1"
    )[0]

print(answer)
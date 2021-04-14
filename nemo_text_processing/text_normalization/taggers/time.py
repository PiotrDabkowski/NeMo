# Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
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


from nemo_text_processing.text_normalization.data_loader_utils import get_abs_path
from nemo_text_processing.text_normalization.graph_utils import (
    NEMO_DIGIT,
    GraphFst,
    convert_space,
    delete_extra_space,
    delete_space,
    insert_space,
)
from nemo_text_processing.text_normalization.taggers.cardinal import CardinalFst

try:
    import pynini
    from pynini.lib import pynutil

    PYNINI_AVAILABLE = True
except (ModuleNotFoundError, ImportError):
    PYNINI_AVAILABLE = False


class TimeFst(GraphFst):
    """
    Finite state transducer for classifying time
        e.g. twelve thirty -> time { hours: "12" minutes: "30" }
        e.g. twelve past one -> time { minutes: "12" hours: "1" }
        e.g. two o clock a m -> time { hours: "2" suffix: "a.m." }
    """

    def __init__(self):
        super().__init__(name="time", kind="classify")
        # hours, minutes, seconds, suffix, zone, style, speak_period

        suffix_graph = pynini.invert(pynini.string_file(get_abs_path("data/time_suffix.tsv")))
        time_zone_graph = pynini.string_file(get_abs_path("data/time_zone.tsv"))

        # only used for < 1000 thousand -> 0 weight
        cardinal = pynutil.add_weight(CardinalFst().graph, weight=-0.7)

        labels_hour = [str(x) for x in range(0, 24)]
        labels_minute_single = [str(x) for x in range(1, 10)]
        labels_minute_double = [str(x) for x in range(10, 60)]

        delete_leading_zero_to_double_digit = (NEMO_DIGIT + NEMO_DIGIT) | (
            pynini.closure(pynutil.delete("0"), 0, 1) + NEMO_DIGIT
        )

        graph_hour = delete_leading_zero_to_double_digit @ pynini.union(*labels_hour) @ cardinal

        graph_minute_single = pynini.union(*labels_minute_single) @ cardinal
        graph_minute_double = pynini.union(*labels_minute_double) @ cardinal
        oclock = pynutil.insert("o'clock")

        final_graph_hour = pynutil.insert("hours: \"") + graph_hour + pynutil.insert("\"")
        final_graph_minute = (
            pynutil.insert("minutes: \"")
            + (pynini.cross("0", "o") + insert_space + graph_minute_single | graph_minute_double)
            + pynutil.insert("\"")
        )
        final_suffix = pynutil.insert("suffix: \"") + convert_space(suffix_graph) + pynutil.insert("\"")
        final_suffix_optional = pynini.closure(delete_space + insert_space + final_suffix, 0, 1)
        final_time_zone_optional = pynini.closure(
            delete_space
            + insert_space
            + pynutil.insert("zone: \"")
            + convert_space(time_zone_graph)
            + pynutil.insert("\""),
            0,
            1,
        )

        # five o' clock
        # two o eight, two thiry five (am/pm)
        # two pm/am
        graph_hm = (
            final_graph_hour
            + pynutil.delete(pynini.union(":", "."))
            + (pynutil.delete("00") | insert_space + final_graph_minute)
            + final_suffix_optional
            + final_time_zone_optional
        )
        graph_h = final_graph_hour + delete_space + insert_space + final_suffix + final_time_zone_optional
        final_graph = (graph_hm | graph_h).optimize()

        final_graph = self.add_tokens(final_graph)
        self.fst = final_graph.optimize()
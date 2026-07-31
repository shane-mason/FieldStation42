import logging
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fs42.block_plan import BlockPlanEntry
from fs42.fluid_builder import FluidBuilder
from fs42.media_processor import MediaProcessor
from fs42.reel_cutter import ReelCutter


class CommercialBreakSelectionTests(unittest.TestCase):
    def test_safe_breaks_ignore_opening_credits_and_nearby_black_frames(self):
        detected = [
            {"chapter_start": 0, "chapter_end": 30},
            {"chapter_start": 30, "chapter_end": 300},
            {"chapter_start": 300, "chapter_end": 320},
            {"chapter_start": 320, "chapter_end": 700},
            {"chapter_start": 700, "chapter_end": 1250},
            {"chapter_start": 1250, "chapter_end": 1320},
        ]
        chapters = [
            {"chapter_start": 0, "chapter_end": 300, "title": "Act 1"},
            {"chapter_start": 300, "chapter_end": 700, "title": "Act 2"},
            {"chapter_start": 700, "chapter_end": 1100, "title": "Act 3"},
            {"chapter_start": 1100, "chapter_end": 1320, "title": "Credits"},
        ]

        segments = MediaProcessor.safe_commercial_segments(
            detected, 1320, chapters
        )

        self.assertEqual(
            [(item["chapter_start"], item["chapter_end"]) for item in segments],
            [(0.0, 300.0), (300.0, 700.0), (700.0, 1320.0)],
        )
        self.assertEqual(sum(item["segment_duration"] for item in segments), 1320)

    def test_black_frame_without_chapter_evidence_is_not_a_break(self):
        black = [
            {"chapter_start": 0, "chapter_end": 420},
            {"chapter_start": 420, "chapter_end": 1320},
        ]
        chapters = [
            {"chapter_start": 0, "chapter_end": 300},
            {"chapter_start": 300, "chapter_end": 1320},
        ]
        self.assertEqual(
            MediaProcessor.safe_commercial_segments(black, 1320, chapters),
            [],
        )

    def test_action_chapter_is_not_mistaken_for_explicit_act_marker(self):
        chapters = [
            {"chapter_start": 0, "chapter_end": 400, "title": "Action Scene"},
            {"chapter_start": 400, "chapter_end": 1320, "title": "Characters"},
        ]
        self.assertEqual(
            MediaProcessor.safe_commercial_segments([], 1320, chapters),
            [],
        )

    def test_credits_chapter_is_not_a_break_even_when_black(self):
        black = [
            {"chapter_start": 0, "chapter_end": 1000},
            {"chapter_start": 1000, "chapter_end": 1500},
        ]
        chapters = [
            {"chapter_start": 0, "chapter_end": 1000, "title": "Final Act"},
            {"chapter_start": 1000, "chapter_end": 1500, "title": "End Credits"},
        ]
        self.assertEqual(
            MediaProcessor.safe_commercial_segments(black, 1500, chapters),
            [],
        )

    def test_no_safe_boundary_does_not_cut_the_feature(self):
        base = SimpleNamespace(
            path="/media/show.mkv",
            duration=1320,
            content_type="feature",
            media_type="video",
        )

        def reel(path):
            return SimpleNamespace(
                make_plan=lambda: [
                    BlockPlanEntry(
                        path,
                        0,
                        15,
                        content_type="bump",
                        media_type="video",
                    )
                ]
            )

        plan = ReelCutter.cut_reels_into_base(
            base_clip=base,
            reel_blocks=[reel("/bumps/black-1.mkv"), reel("/bumps/black-2.mkv")],
            base_offset=0,
            base_duration=1320,
            break_strategy="standard",
            start_bump=None,
            end_bump=None,
            break_points=[],
        )

        self.assertEqual(
            [(item.path, item.skip, item.duration) for item in plan],
            [
                ("/media/show.mkv", 0, 1320),
                ("/bumps/black-1.mkv", 0, 15),
                ("/bumps/black-2.mkv", 0, 15),
            ],
        )

    def test_black_bumpers_are_not_analyzed_as_feature_breaks(self):
        builder = FluidBuilder.__new__(FluidBuilder)
        builder.db_path = "unused.db"
        builder._l = logging.getLogger("test")
        connection = MagicMock()
        connection.cursor.return_value.fetchone.return_value = None
        bumper = SimpleNamespace(
            realpath="/bumps/adult-swim-black.mkv",
            duration=15,
            content_type="bump",
        )

        with (
            patch("fs42.fluid_builder.connect", return_value=connection),
            patch.object(MediaProcessor, "black_detect") as black_detect,
            patch.object(MediaProcessor, "chapter_detect") as chapter_detect,
            patch(
                "fs42.fluid_builder.FluidStatements.add_chapter_points"
            ) as store,
        ):
            builder.scan_chapters_for_entries([bumper])

        black_detect.assert_not_called()
        chapter_detect.assert_not_called()
        store.assert_called_once_with(connection, bumper.realpath, [])


if __name__ == "__main__":
    unittest.main()

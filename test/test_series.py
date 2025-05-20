import pytest
from fs42.series import SeriesIndex

class TestSeriesIndex:

    test_list = ["a/b0/c0.mp4", "a/b0/c1.mp4","a/b0/c2.mp4","a/b0/c3.mp4","a/b0/c4.mp4","a/b0/c5.mp4"]

    def test_key(self):
        seq_key = SeriesIndex.make_key("seriesname", "sequencename")
        assert seq_key == "seriesname-sequencename"

    def test_populating(self):
        series = SeriesIndex("a")
        series.populate(TestSeriesIndex.test_list)
        assert series.get_series_length() == len(TestSeriesIndex.test_list)

    def test_next_episode(self):
        series = SeriesIndex("a")
        series.populate(TestSeriesIndex.test_list)
        episode = series.get_next()
        assert episode == TestSeriesIndex.test_list[0]
        episode = series.get_next()
        assert episode == TestSeriesIndex.test_list[1]
        episode = series.get_next()
        assert episode == TestSeriesIndex.test_list[2]
        
        for i in range(series.get_series_length() * 3):
            episode = series.get_next()
            assert episode




            
    

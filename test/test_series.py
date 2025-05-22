import pytest
from fs42.series import SeriesIndex

@pytest.fixture
def test_list():
    return [
        "a/b0/c0.mp4",
        "a/b0/c1.mp4",
        "a/b0/c2.mp4",
        "a/b0/c3.mp4",
        "a/b0/c4.mp4",
        "a/b0/c5.mp4",
    ]

def test_key():
    seq_key = SeriesIndex.make_key("seriesname", "sequencename")
    assert seq_key == "seriesname-sequencename"

def test_populating(test_list):
    series = SeriesIndex("a")
    series.populate(test_list)
    assert series.get_series_length() == len(test_list)

def test_next_episode(test_list):
    series = SeriesIndex("a")
    series.populate(test_list)
    expected_episodes = ["a/b0/c0.mp4", "a/b0/c1.mp4","a/b0/c2.mp4","a/b0/c3.mp4","a/b0/c4.mp4","a/b0/c5.mp4"]
    episodes = [series.get_next() for _ in expected_episodes]
    assert episodes == expected_episodes

def test_next_episode_complex():
    test_list = [
        "prime/avatar/Avatar - The Last Airbender - S01E02 - The Avatar Returns.mkv",
        "prime/avatar/Avatar - The Last Airbender - S01E01 - The Boy in the Iceberg.mkv",
        "prime/avatar/Avatar - The Last Airbender - S01E06 - Imprisoned.mkv",
        "prime/avatar/Avatar - The Last Airbender - S01E04 - The Warriors of Kyoshi.mkv",
        "prime/avatar/Avatar - The Last Airbender - S01E03 - The Southern Air Temple.mk" ,
        "prime/avatar/Avatar - The Last Airbender - S01E05 - The King of Omashu.mkv",
    ]

    expected_episodes = [
        "prime/avatar/Avatar - The Last Airbender - S01E01 - The Boy in the Iceberg.mkv",
        "prime/avatar/Avatar - The Last Airbender - S01E02 - The Avatar Returns.mkv",
        "prime/avatar/Avatar - The Last Airbender - S01E03 - The Southern Air Temple.mk" ,
        "prime/avatar/Avatar - The Last Airbender - S01E04 - The Warriors of Kyoshi.mkv",
        "prime/avatar/Avatar - The Last Airbender - S01E05 - The King of Omashu.mkv",
        "prime/avatar/Avatar - The Last Airbender - S01E06 - Imprisoned.mkv",
    ]
    
    series = SeriesIndex("avatar")
    series.populate(file_list=test_list)
    episodes = [series.get_next() for _ in expected_episodes]
    assert episodes == expected_episodes


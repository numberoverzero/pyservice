from pyservice import common


def test_container_missing():
    container = common.Container()
    assert container.missing is None

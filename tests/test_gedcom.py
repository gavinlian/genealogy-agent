import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from gedcom import export_family_to_gedcom, import_gedcom_text


def test_gedcom_roundtrip_basic():
    family = {"name": "张氏族谱", "surname": "张"}
    persons = [
        {"id": "p1", "name": "张三", "gender": "male", "birth_year": 1900},
        {"id": "p2", "name": "张四", "gender": "male", "birth_year": 1920, "courtesy_name": "子明"},
    ]
    relations = [
        {"from_person_id": "p1", "to_person_id": "p2", "relation_type": "parent_child"},
    ]
    gedcom = export_family_to_gedcom(family, persons, relations)
    assert "0 @Ip1@ INDI" in gedcom or "INDI" in gedcom
    assert "张三" in gedcom
    assert "_CN字 子明" in gedcom

    parsed = import_gedcom_text(gedcom)
    assert len(parsed["persons"]) >= 2
    assert parsed["family"]["surname"] == "张" or parsed["family"]["name"]

import pytest

from scripts.migrate_phone import plan_updates


def test_matches_source_not_dataset_id():
    dataset = [{"id": "1413", "source_url": "listing-a", "phone": "51 966 359 424"}]
    properties = [dict(id=1351, source_url="listing-a", phone=None),
                  dict(id=1413, source_url="listing-b", phone=None)]
    changes, _ = plan_updates(dataset, properties)
    assert changes == [dict(id=1351, source_url="listing-a", previous_phone=None, phone="51 966 359 424")]


def test_preserves_existing_contact():
    changes, counts = plan_updates([dict(source_url="a", phone="new")],
                                   [dict(id=1, source_url="a", phone="existing")])
    assert changes == []
    assert counts["telefono_existente_conservado"] == 1


def test_rejects_conflicting_sources_before_writing():
    with pytest.raises(ValueError):
        plan_updates([dict(source_url="a", phone="one"), dict(source_url="a", phone="two")], [])


def test_empty_contact_can_be_filled_without_losing_original_value_in_backup():
    changes, _ = plan_updates([dict(source_url="a", phone="123")],
                              [dict(id=2, source_url="a", phone="  ")])
    assert changes[0]["previous_phone"] == "  "


def test_missing_source_or_phone_cannot_overwrite_properties():
    changes, _ = plan_updates([dict(id=1, phone="123"), dict(source_url="a", phone=None)],
                              [dict(id=1, source_url="a", phone=None)])
    assert changes == []


def test_second_run_is_idempotent():
    dataset = [dict(source_url="a", phone="123")]
    assert len(plan_updates(dataset, [dict(id=1, source_url="a", phone=None)])[0]) == 1
    assert plan_updates(dataset, [dict(id=1, source_url="a", phone="123")])[0] == []

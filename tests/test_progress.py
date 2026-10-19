from dashcamutils import helpers


def test_repair_progress_has_read_and_write_phases(tmp_path, monkeypatch, caplog):
    files = [tmp_path / "first.jpg", tmp_path / "second.jpg"]
    for imagefile in files:
        imagefile.touch()
    missing = tmp_path / "missing.jpg"
    line = "GARMIN 03/21/2026 21:14:57 41.89173 -87.66727 5 MPH"
    monkeypatch.setattr(helpers, "read_timestamp", lambda imagefile, skip_ocr: line)
    monkeypatch.setattr(helpers, "update_metadata", lambda *args, **kwargs: None)
    monkeypatch.setattr(helpers, "adjust_image", lambda *args: None)

    with caplog.at_level("INFO"):
        assert (
            helpers.process_batch(
                [str(files[0]), str(missing), str(files[1])],
                helpers.Settings(),
            )
            is True
        )

    messages = [record.getMessage() for record in caplog.records]
    assert f"[1/2] OCR-reading {files[0]}" in messages
    assert f"[2/2] OCR-reading {files[1]}" in messages
    assert f"[1/2] writing {files[0]}" in messages
    assert f"[2/2] writing {files[1]}" in messages
    assert any(f"Image file {missing} not found" in message for message in messages)

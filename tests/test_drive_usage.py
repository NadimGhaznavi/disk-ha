"""Verify filesystem usage and configuration-backed drive presentation."""

import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from diskha.interface.DriveUsage import read_usage
from diskha.server.DrivePage import render_page


def drive_settings():
    return {role: {"path": f"/disk{number}/{'archive/incoming/movies' if role == 'source' else 'inbox/media-center'}",
                   "mount": f"/disk{number}", "uuid": f"uuid-{number}", "disk": f"/dev/disk/by-id/ata-drive{number}",
                   "capacity": number * 4 * 10**12, "used": 3.125 * 10**12, "free": 10**12}
            for number, role in enumerate(("source", "target"), 1)}


class DriveUsageTests(unittest.TestCase):
    def test_unmounted_path_does_not_read_root_filesystem_usage(self):
        with patch("diskha.interface.DriveUsage.os.path.ismount", return_value=False), \
                patch("diskha.interface.DriveUsage.shutil.disk_usage") as usage:
            self.assertIsNone(read_usage("/exports/disk1"))
        usage.assert_not_called()

    def test_mounted_path_reads_byte_counts(self):
        expected = SimpleNamespace(total=8 * 10**12, used=3 * 10**12)
        with patch("diskha.interface.DriveUsage.os.path.ismount", return_value=True), \
                patch("diskha.interface.DriveUsage.shutil.disk_usage", return_value=expected) as usage:
            self.assertIs(read_usage("/exports/disk2"), expected)
        usage.assert_called_once_with("/exports/disk2")

    def test_page_uses_saved_directories_and_formats_terabytes(self):
        with patch("diskha.server.DrivePage.read_drives", return_value=drive_settings()):
            page = render_page().decode()
        self.assertIn('/disk1/archive/incoming/movies', page)
        self.assertIn('/disk2/inbox/media-center', page)
        self.assertIn('<td>4.00</td><td>3.12</td><td>1.00</td>', page)
        self.assertIn('<td>8.00</td><td>3.12</td><td>1.00</td>', page)
        self.assertNotIn('/exports/', page)
        self.assertNotIn('{{drive_configuration}}', page)
        self.assertIn('id="save-drives" type="button" disabled', page)

    def test_unavailable_readings_and_escaped_directory_names(self):
        settings = copy.deepcopy(drive_settings())
        settings['source'].update(path='/disk1/<movies & "shows">', capacity=None, used=None, free=None,
                                  error='Mount <missing>')
        with patch("diskha.server.DrivePage.read_drives", return_value=settings):
            page = render_page().decode()
        self.assertIn('<td>Unavailable</td>', page)
        self.assertIn('/disk1/&lt;movies &amp; &quot;shows&quot;&gt;', page)
        self.assertIn('Mount &lt;missing&gt;', page)
        self.assertNotIn('<missing>', page)
        with patch("diskha.server.DrivePage.read_drives", side_effect=OSError('not installed')):
            self.assertIn('Drive settings unavailable', render_page().decode())

    def test_directory_names_with_template_syntax_remain_literal(self):
        settings = drive_settings()
        settings['source']['path'] = '/disk1/{{health}}/{{email_notification}}'
        with patch("diskha.server.DrivePage.read_drives", return_value=settings):
            page = render_page().decode()
        self.assertIn('value="/disk1/{{health}}/{{email_notification}}"', page)


if __name__ == "__main__":
    unittest.main()

import http.client
import unittest
from urllib.parse import urlencode

from fluxio_wifi.controller import Credentials
from fluxio_wifi.nm import Network
from fluxio_wifi.portal import PortalServer, render_wifi_form, validate_form


class FakeController:
    def __init__(self):
        self.networks = [Network("Home", 70, True), Network("Cafe", 40, False)]
        self.last_error = ""
        self.submitted = []
        self.accept = True
        self.mode = "ap"

    def submit(self, creds):
        if not self.accept:
            return False
        self.submitted.append(creds)
        return True


class ValidateFormTest(unittest.TestCase):
    def test_typed_name_wins_over_the_list(self):
        creds, error = validate_form({"ssid": ["Home"], "ssid_other": ["  Lab  "], "password": ["password1"]})
        self.assertEqual((creds, error), (Credentials("Lab", "password1"), ""))

    def test_open_network(self):
        creds, _ = validate_form({"ssid": ["Cafe"], "password": [""]})
        self.assertEqual(creds, Credentials("Cafe", ""))

    def test_errors(self):
        cases = [
            {"ssid": [""], "password": ["password1"]},
            {"ssid_other": ["x" * 33], "password": ["password1"]},
            {"ssid": ["Home"], "password": ["short"]},
            {"ssid": ["Home"], "password": ["p" * 64]},
        ]
        for form in cases:
            with self.subTest(form=form):
                creds, error = validate_form(form)
                self.assertIsNone(creds)
                self.assertTrue(error)

    def test_password_never_shows_in_repr(self):
        self.assertNotIn("password1", repr(Credentials("Home", "password1")))


class RenderTest(unittest.TestCase):
    def test_ssids_are_escaped(self):
        page = render_wifi_form([Network("<script>alert(1)</script>'", 50, True)])
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("value='<", page)

    def test_error_is_shown(self):
        self.assertIn("Could not connect", render_wifi_form([], "Could not connect to Home"))


class PortalServerTest(unittest.TestCase):
    def setUp(self):
        self.controller = FakeController()
        self.portal = PortalServer(self.controller, "esp32_C209DAB7022B", "127.0.0.1", 0).start()

    def tearDown(self):
        self.portal.close()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.portal.port, timeout=5)
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        data = resp.read().decode()
        conn.close()
        return resp, data

    def post_wifi(self, fields):
        return self.request(
            "POST", "/wifi", urlencode(fields), {"Content-Type": "application/x-www-form-urlencoded"}
        )

    def test_home_shows_device_id(self):
        resp, body = self.request("GET", "/")
        self.assertEqual(resp.status, 200)
        self.assertIn("esp32_C209DAB7022B", body)

    def test_wifi_page_lists_networks_and_last_error(self):
        self.controller.last_error = "Could not connect to Home: bad password"
        _, body = self.request("GET", "/wifi")
        self.assertIn("Home (70%)", body)
        self.assertIn("Cafe (40%, open)", body)
        self.assertIn("bad password", body)

    def test_unknown_paths_redirect_home(self):
        resp, _ = self.request("GET", "/generate_204", headers={"Host": "connectivitycheck.gstatic.com"})
        self.assertEqual(resp.status, 302)
        self.assertEqual(resp.getheader("Location"), "/")

    def test_valid_post_submits(self):
        resp, body = self.post_wifi({"ssid": "Home", "password": "password1"})
        self.assertEqual(resp.status, 200)
        self.assertIn("Connecting to Home", body)
        self.assertIn("access point turns off", body)
        self.assertEqual(self.controller.submitted, [Credentials("Home", "password1")])

    def test_post_from_the_regular_network_explains_the_switch(self):
        self.controller.mode = "monitor"
        _, body = self.post_wifi({"ssid": "Lab", "password": "password2"})
        self.assertIn("leaving this network", body)

    def test_invalid_post_shows_the_form_again(self):
        _, body = self.post_wifi({"ssid": "Home", "password": "short"})
        self.assertIn("8 to 63 characters", body)
        self.assertEqual(self.controller.submitted, [])

    def test_busy_controller(self):
        self.controller.accept = False
        _, body = self.post_wifi({"ssid": "Home", "password": "password1"})
        self.assertIn("Already trying", body)

    def test_oversized_post_is_rejected(self):
        resp, _ = self.post_wifi({"ssid": "Home", "password": "x" * 5000})
        self.assertEqual(resp.status, 400)


if __name__ == "__main__":
    unittest.main()

import unittest


class PearPalBridgeTests(unittest.TestCase):
    def test_provider_keeps_original_labels_and_default_hidden_state(self):
        from nuannuan._pearpal.pearpal_provider import OfficialPearPalProvider
        provider = OfficialPearPalProvider(enabled=True)
        self.assertEqual([item.id for item in provider.list_labels()],
                         ['pearpal_star', 'pearpal_dewdrop', 'pearpal_box', 'pearpal_read'])
        self.assertTrue(provider.get_user_status()['hide_awarded'])

    def test_adapter_preserves_original_projection_and_material_names(self):
        from nuannuan._pearpal.models import MapMaskPoint
        from nuannuan.pearpal_bridge import adapt_points
        point = MapMaskPoint('p1', 'pearpal_star', '奇想星', 'miraland', 123.5, 456.25)
        converted = adapt_points([point])[0]
        self.assertEqual((converted.x, converted.y), (123.5, 456.25))
        self.assertEqual(converted.label, '奇想星')

    def test_login_payload_only_accepts_expected_official_origin(self):
        from nuannuan.pearpal_bridge import credentials_from_page
        with self.assertRaises(ValueError):
            credentials_from_page('cn', 'https://example.com', {})

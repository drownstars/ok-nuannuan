"""Original Whimbox 3.1.1 provider/auth tests, imports adapted only; GPL-3.0."""

import json, os, tempfile, threading, time, unittest
from pathlib import Path
from unittest.mock import Mock, patch
import numpy as np

from nuannuan.pearpal._pearpal.models import MapMaskPoint, MapMaskViewport

from nuannuan.pearpal._pearpal.pearpal_provider import OfficialPearPalProvider

from nuannuan.pearpal._pearpal.pearpal_auth import (
    PearPalAwardedState,
    PearPalCredentials,
    PearPalUserClient,
    decode_user_info,
    parse_login_storage,
)

class FakePearPalClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def fetch_catalog(self, world_id: str):
        if self.fail:
            raise RuntimeError("public API unavailable")
        return {
            "data": {
                "list": [
                    {
                        "id": 2,
                        "name": "收集物",
                        "catalogs": [
                            {"id": 11, "name": "奇想星", "icon": "star.png"},
                            {"id": 12, "name": "\u7075\u611f\u9732\u73e0", "icon": "dewdrop.png"},
                            {"id": 999, "name": "阶段入口"},
                        ],
                    },
                    {
                        "id": 14,
                        "name": "宝箱",
                        "catalogs": [
                            {"id": 13, "name": "普通宝箱", "icon": "box.png"},
                        ],
                    },
                    {
                        "id": 15,
                        "name": "任务活动",
                        "catalogs": [
                            {"id": 20, "name": "阅读物", "icon": "read.png"},
                        ],
                    },
                ]
            }
        }, None

    def fetch_spawners(self, world_id: str):
        return [
            {"id": 100, "world_id": 1, "catalog": 11, "x": 100, "y": 200},
            {"id": 101, "world_id": 1, "catalog": 12, "x": 150, "y": 250},
            {"id": 102, "world_id": 1, "catalog": 20, "x": 200, "y": 300},
            {
                "id": 200,
                "world_id": 1,
                "catalog": 999,
                "x": 300,
                "y": 400,
                "stage_id": "stage-1",
            },
            {"id": 300, "world_id": 1, "catalog": 999, "x": 500, "y": 600},
        ], None

    def fetch_stage_spawners(self):
        return {
            "stage-1": [
                {"id": 201, "catalog": 13, "description": "阶段宝箱"},
            ]
        }, None

class FakeWanxiangPearPalClient(FakePearPalClient):
    def fetch_spawners(self, world_id: str):
        if str(world_id) != "4020034":
            return super().fetch_spawners(world_id)
        return [
            {
                "id": 400,
                "world_id": 4020034,
                "catalog": 244,
                "x": 100640.648268,
                "y": 57032.078271,
            },
            {
                "id": 401,
                "world_id": 4020034,
                "catalog": 245,
                "x": 120000,
                "y": 90000,
            },
            {
                "id": 402,
                "world_id": 4020034,
                "catalog": 20,
                "x": 140000,
                "y": 100000,
            },
            {
                "id": 403,
                "world_id": 4020034,
                "catalog": 13,
                "x": 160000,
                "y": 120000,
            },
        ], None

class FakePearPalUserClient:
    def fetch_awarded_state(self, credentials: PearPalCredentials):
        if credentials.openid != "12405094":
            raise RuntimeError("unexpected user")
        return PearPalAwardedState(
            star_ids=frozenset({"100"}),
            box_ids=frozenset(),
            dewdrop_ids=frozenset({"101"}),
            read_ids=frozenset({"102"}),
        )

class MutablePearPalUserClient:
    def __init__(self) -> None:
        self.calls = 0
        self.error: Exception | None = None
        self.awarded_state = PearPalAwardedState(
            star_ids=frozenset({"100"}),
            box_ids=frozenset(),
            dewdrop_ids=frozenset({"101"}),
        )

    def fetch_awarded_state(self, credentials: PearPalCredentials):
        if credentials.openid != "12405094":
            raise RuntimeError("unexpected user")
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.awarded_state

class OfficialPearPalProviderTests(unittest.TestCase):
    def test_listing_labels_does_not_start_point_loading(self) -> None:
        client = FakePearPalClient()
        client.fetch_catalog = Mock(wraps=client.fetch_catalog)
        provider = OfficialPearPalProvider(
            enabled=True,
            client=client,
            background=False,
        )

        labels = provider.list_labels()

        self.assertEqual(len(labels), 4)
        self.assertEqual(
            provider.get_data_status()["points_source"],
            "pearpal-public-idle",
        )
        client.fetch_catalog.assert_not_called()

        provider.list_points(label_ids=[])

        self.assertEqual(
            [call.args[0] for call in client.fetch_catalog.call_args_list],
            ["1", "4020034"],
        )
        self.assertEqual(
            provider.get_data_status()["points_source"],
            "pearpal-public-ready",
        )

    def test_loads_supported_collectibles_and_expands_stage_child(self) -> None:
        provider = OfficialPearPalProvider(
            enabled=True,
            client=FakePearPalClient(),
            background=False,
        )

        labels = provider.list_labels()
        points = provider.list_points()
        point_by_id = {point.id: point for point in points}

        self.assertEqual(
            [label.id for label in labels],
            [
                "pearpal_star",
                "pearpal_dewdrop",
                "pearpal_box",
                "pearpal_read",
            ],
        )
        self.assertEqual(
            set(point_by_id),
            {
                "pearpal:100",
                "pearpal:101",
                "pearpal:102",
                "pearpal:201",
            },
        )
        self.assertEqual(point_by_id["pearpal:100"].label_id, "pearpal_star")
        self.assertAlmostEqual(
            point_by_id["pearpal:100"].image_x,
            2.2222222222222223,
        )
        self.assertAlmostEqual(
            point_by_id["pearpal:100"].image_y,
            4.444444444444445,
        )
        dewdrop = point_by_id["pearpal:101"]
        self.assertEqual(dewdrop.label_id, "pearpal_dewdrop")
        self.assertAlmostEqual(dewdrop.image_x, 3.3333333333333335)
        self.assertAlmostEqual(dewdrop.image_y, 5.555555555555555)
        self.assertEqual(point_by_id["pearpal:102"].label_id, "pearpal_read")
        stage_box = point_by_id["pearpal:201"]
        self.assertEqual(stage_box.label_id, "pearpal_box")
        self.assertAlmostEqual(stage_box.image_x, 6.666666666666667)
        self.assertAlmostEqual(stage_box.image_y, 8.88888888888889)
        self.assertEqual(stage_box.detail["parent_stage_id"], "stage-1")
        self.assertTrue(stage_box.detail["is_stage_expanded"])
        self.assertEqual(provider.get_data_status()["points_source"], "pearpal-public-ready")

    def test_current_api_anchor_maps_near_checkpoint_png_position(self) -> None:
        client = FakePearPalClient()
        client.fetch_spawners = Mock(
            return_value=(
                [
                    {
                        "id": 1399,
                        "world_id": 1,
                        "catalog": 11,
                        "x": 923326.871094,
                        "y": 895070.148438,
                    }
                ],
                None,
            )
        )
        client.fetch_stage_spawners = Mock(return_value=({}, None))
        provider = OfficialPearPalProvider(
            enabled=True,
            client=client,
            background=False,
        )

        point = provider.list_points()[0]

        self.assertEqual(point.id, "pearpal:1399")
        self.assertAlmostEqual(point.image_x, 20526.281163, delta=15.0)
        self.assertAlmostEqual(point.image_y, 19892.919618, delta=15.0)

    def test_filters_by_label_and_map(self) -> None:
        provider = OfficialPearPalProvider(
            enabled=True,
            client=FakePearPalClient(),
            background=False,
        )

        stars = provider.list_points(label_ids=["pearpal_star"], map_name="miraland")

        self.assertEqual([point.id for point in stars], ["pearpal:100"])
        self.assertEqual(provider.list_points(map_name="unsupported"), [])
        self.assertEqual(provider.list_points(label_ids=[]), [])

    def test_loads_and_filters_wanxiang_collectibles(self) -> None:
        provider = OfficialPearPalProvider(
            enabled=True,
            client=FakeWanxiangPearPalClient(),
            background=False,
        )

        points = provider.list_points(map_name="wanxiang")
        point_by_id = {point.id: point for point in points}

        self.assertEqual(
            set(point_by_id),
            {
                "pearpal:4020034:400",
                "pearpal:4020034:401",
                "pearpal:4020034:402",
                "pearpal:4020034:403",
            },
        )
        self.assertEqual(point_by_id["pearpal:4020034:400"].label_id, "pearpal_star")
        self.assertEqual(point_by_id["pearpal:4020034:401"].label_id, "pearpal_dewdrop")
        self.assertEqual(point_by_id["pearpal:4020034:402"].label_id, "pearpal_read")
        self.assertEqual(point_by_id["pearpal:4020034:403"].label_id, "pearpal_box")
        self.assertAlmostEqual(
            point_by_id["pearpal:4020034:400"].image_x,
            100640.648268 * 2 / 90,
        )
        self.assertAlmostEqual(
            point_by_id["pearpal:4020034:400"].image_y,
            57032.078271 * 2 / 90,
        )
        self.assertTrue(all(point.map_name == "wanxiang" for point in points))
        self.assertFalse(
            any(point.map_name == "wanxiang" for point in provider.list_points(map_name="miraland"))
        )

    def test_public_api_error_is_reported_without_sample_fallback(self) -> None:
        provider = OfficialPearPalProvider(
            enabled=True,
            client=FakePearPalClient(fail=True),
            background=False,
        )

        self.assertEqual(provider.list_points(), [])
        status = provider.get_data_status()
        self.assertEqual(status["points_source"], "pearpal-public-error")
        self.assertIn("public API unavailable", status["points_error"])

class PearPalUserStateTests(unittest.TestCase):
    def test_user_client_uses_region_specific_api_and_client_id(self) -> None:
        cn_client = PearPalUserClient(region="cn")
        oversea_client = PearPalUserClient(region="oversea")

        self.assertEqual(cn_client.client_id, 1106)
        self.assertEqual(
            cn_client.user_info_url,
            "https://myl-api.nuanpaper.com/v1/strategy/map/user/info",
        )
        self.assertEqual(oversea_client.client_id, 1116)
        self.assertEqual(
            oversea_client.user_info_url,
            "https://pearpal-api.infoldgames.com/v1/strategy/map/user/info",
        )

    def test_parses_login_storage_and_user_info_ids(self) -> None:
        credentials = parse_login_storage(
            '{"token":"abcDEF0123456789","time":1786062221854}',
            '"12405094"',
        )
        awarded = decode_user_info(
            {
                "code": 0,
                "data": {
                    "star": [100, "101", None],
                    "box": [201, 202],
                    "dewdrop": [301, 302],
                    "read": [401, 402],
                },
            }
        )

        self.assertEqual(credentials.openid, "12405094")
        self.assertEqual(credentials.masked_openid, "12****94")
        self.assertEqual(awarded.star_ids, frozenset({"100", "101"}))
        self.assertEqual(awarded.box_ids, frozenset({"201", "202"}))
        self.assertEqual(awarded.dewdrop_ids, frozenset({"301", "302"}))
        self.assertEqual(awarded.read_ids, frozenset({"401", "402"}))

    def test_login_filters_awarded_points_and_can_show_them(self) -> None:
        credentials = PearPalCredentials(
            token="abcDEF0123456789",
            openid="12405094",
        )
        provider = OfficialPearPalProvider(
            enabled=True,
            client=FakePearPalClient(),
            background=False,
            user_client=FakePearPalUserClient(),
            auth_background=False,
        )
        self.assertEqual(
            {point.id for point in provider.list_points()},
            {
                "pearpal:100",
                "pearpal:101",
                "pearpal:102",
                "pearpal:201",
            },
        )

        status = provider.authenticate(credentials)

        self.assertTrue(status["authenticated"])
        self.assertEqual(status["matched_awarded_star_count"], 1)
        self.assertEqual(status["matched_awarded_dewdrop_count"], 1)
        self.assertEqual(status["matched_awarded_read_count"], 1)
        self.assertEqual(
            [point.id for point in provider.list_points()],
            ["pearpal:201"],
        )
        provider.set_hide_awarded(False)
        star = provider.get_point_detail("pearpal:100")
        self.assertTrue(star["detail"]["awarded"])
        self.assertFalse(star["detail"]["anonymous"])
        provider.disconnect_user()
        self.assertEqual(len(provider.list_points()), 4)

    def test_switching_region_resets_login_and_reloads_public_points(self) -> None:
        credentials = PearPalCredentials(
            token="abcDEF0123456789",
            openid="12405094",
        )
        client = FakePearPalClient()
        client.fetch_catalog = Mock(wraps=client.fetch_catalog)
        provider = OfficialPearPalProvider(
            enabled=True,
            client=client,
            background=False,
            user_client=FakePearPalUserClient(),
            auth_background=False,
        )
        provider.list_points()
        provider.authenticate(credentials)

        status = provider.set_region("oversea")

        self.assertEqual(status["region"], "oversea")
        self.assertFalse(status["authenticated"])
        self.assertEqual(
            provider.get_data_status()["points_source"],
            "pearpal-public-idle",
        )
        self.assertEqual(len(provider.list_points()), 4)
        # Current pinned provider loads both supported worlds on each region load.
        self.assertEqual(client.fetch_catalog.call_count, 4)

    def test_clear_login_information_removes_backend_session(self) -> None:
        credentials = PearPalCredentials(
            token="abcDEF0123456789",
            openid="12405094",
        )
        provider = OfficialPearPalProvider(
            enabled=True,
            client=FakePearPalClient(),
            background=False,
            user_client=FakePearPalUserClient(),
            auth_background=False,
        )
        provider.list_points()
        self.assertTrue(provider.authenticate(credentials)["authenticated"])

        status = provider.clear_login_information()
        self.assertFalse(status["authenticated"])
        self.assertEqual(status["auth_state"], "anonymous")
        self.assertEqual(len(provider.list_points()), 4)

    def test_clear_login_information_invalidates_in_flight_login(self) -> None:
        credentials = PearPalCredentials(
            token="abcDEF0123456789",
            openid="12405094",
        )
        auth_started = threading.Event()
        release_auth = threading.Event()

        class DelayedPearPalUserClient:
            def fetch_awarded_state(self, received: PearPalCredentials):
                auth_started.set()
                release_auth.wait(timeout=2.0)
                return FakePearPalUserClient().fetch_awarded_state(received)

        provider = OfficialPearPalProvider(
            enabled=True,
            client=FakePearPalClient(),
            background=False,
            user_client=DelayedPearPalUserClient(),
            auth_background=True,
        )

        provider.authenticate(credentials)
        self.assertTrue(auth_started.wait(timeout=1.0))
        provider.clear_login_information()
        release_auth.set()
        auth_thread = provider._auth_thread
        if auth_thread is not None:
            auth_thread.join(timeout=2.0)

        status = provider.get_user_status()
        self.assertFalse(status["authenticated"])
        self.assertEqual(status["auth_state"], "anonymous")

    def test_user_state_refresh_does_not_rebuild_all_points(self) -> None:
        credentials = PearPalCredentials(
            token="abcDEF0123456789",
            openid="12405094",
        )
        provider = OfficialPearPalProvider(
            enabled=True,
            client=FakePearPalClient(),
            background=False,
            user_client=FakePearPalUserClient(),
            auth_background=False,
        )
        provider.list_points()
        original_points = provider._points
        original_point_by_id = provider._point_by_id

        provider.authenticate(credentials)
        provider.list_points()
        provider.get_user_status()
        self.assertIs(provider._points, original_points)
        self.assertIs(provider._point_by_id, original_point_by_id)
        self.assertFalse(
            hasattr(provider, "_decorated_points_cache")
        )

        provider.disconnect_user()
        self.assertIs(provider._points, original_points)
        self.assertIs(provider._point_by_id, original_point_by_id)

    def test_auto_refresh_manual_refresh_and_failure_backoff(self) -> None:
        credentials = PearPalCredentials(
            token="abcDEF0123456789",
            openid="12405094",
        )
        user_client = MutablePearPalUserClient()
        clock = [100.0]
        provider = OfficialPearPalProvider(
            enabled=True,
            client=FakePearPalClient(),
            background=False,
            user_client=user_client,
            auth_background=False,
            refresh_background=False,
        )

        with patch(
            "nuannuan.pearpal._pearpal.pearpal_provider.time.monotonic",
            side_effect=lambda: clock[0],
        ):
            provider.list_points()
            login_status = provider.authenticate(credentials)
            self.assertEqual(user_client.calls, 1)
            self.assertEqual(login_status["last_refresh_reason"], "login")

            user_client.awarded_state = PearPalAwardedState(
                star_ids=frozenset(),
                box_ids=frozenset({"201"}),
                dewdrop_ids=frozenset(),
            )
            clock[0] = 106.0
            provider.note_overlay_activity(is_bigmap_open=False)
            provider.note_overlay_activity(is_bigmap_open=True)
            self.assertEqual(user_client.calls, 2)
            self.assertEqual(
                provider.get_user_status()["last_refresh_reason"],
                "map-open",
            )
            self.assertEqual(
                {point.id for point in provider.list_points()},
                {
                    "pearpal:100",
                    "pearpal:101",
                    "pearpal:102",
                },
            )

            clock[0] = 137.0
            provider.note_overlay_activity(is_bigmap_open=True)
            self.assertEqual(user_client.calls, 3)
            self.assertEqual(
                provider.get_user_status()["last_refresh_reason"],
                "periodic",
            )

            user_client.error = RuntimeError("temporary API error")
            failed_status = provider.refresh_user_state()
            self.assertEqual(user_client.calls, 4)
            self.assertEqual(failed_status["refresh_failure_count"], 1)
            self.assertIn("temporary API error", failed_status["refresh_error"])
            self.assertAlmostEqual(
                failed_status["next_refresh_in_seconds"],
                5.0,
            )
            self.assertTrue(
                provider.get_point_detail("pearpal:201")["detail"]["awarded"]
            )

            clock[0] = 138.0
            provider.note_overlay_activity(is_bigmap_open=True)
            self.assertEqual(user_client.calls, 4)

            user_client.error = None
            clock[0] = 142.0
            provider.note_overlay_activity(is_bigmap_open=True)
            retry_status = provider.get_user_status()
            self.assertEqual(user_client.calls, 5)
            self.assertEqual(retry_status["last_refresh_reason"], "retry")
            self.assertEqual(retry_status["refresh_error"], "")

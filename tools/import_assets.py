"""Convert supplied Whimbox visual assets to editable ok-script templates.

Does not import or execute Whimbox modules. Source images are never changed.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FEATURES = [
    'IconPageMainFeature', 'IconPickupFeature', 'IconSkipDialog', 'IconSkip', 'IconClickSkip',
    'IconDailyRewardFeature1', 'IconDailyRewardFeature2',
    'ButtonDigGather', 'ButtonDigGatherConfirm', 'ButtonDigAgain',
    'ButtonZxxyEntrance', 'IconZxxyFeature', 'IconZxxyTaskFinished',
    'IconPhotoFeature', 'IconPhotoEdit', 'ButtonMonthlyPassAward',
    'ButtonXhsgEntrance', 'IconXhsgFeature', 'IconXhsgTaskFinished', 'ButtonXhsgBooklookLike',
    'IconXhsgGroupChatFeature', 'ButtonXhsgBottleClose', 'IconUIBigmap', 'IconUIBigmapJoystick',
    'IconBigMapMaxScale', 'IconBigMapMaxScaleJoyStick', 'ButtonBigMapZoom', 'IconBigMapHomeFeature',
    'IconSetdownFeature', 'ButtonItemSetting', 'ButtonItemFinishSetting', 'ButtonItemPlaceableItem',
    'ButtonItemLanternConfirm', 'IconItemCantPlace',
    'IconAbilityInsect',
    'IconWardrobeFeature', 'IconAbilityFeature', 'ButtonAbilityChangeList', 'ButtonAbilitySave',
]
REGIONS = ['AreaPickup', 'AreaEscEntrances', 'AreaDigingNumText', 'AreaZxxyScore',
           'AreaZxxyRewards', 'AreaMonthlyPassTab1', 'AreaMonthlyPassTab2', 'AreaPageTitleFeature',
           'AreaZxxyTaskText', 'AreaXhsgTaskText', 'AreaXhsgScore', 'AreaXhsgRewards',
           'AreaBigMapRegionName', 'AreaBigMapRegionSelect', 'AreaBigMapTeleportButton',
           'AreaBigMapTeleporterSelect', 'AreaDialog', 'AreaDialogSelection', 'AreaItemFirstItem',
           'AreaMaterialGetText']
REGIONS.append('AreaAbilityButton')
REGIONS.extend(['AreaAbilityChange', 'AreaAbilityPlanChangeButton', 'AreaAbilityPlan1Button',
                'AreaAbilityPlan2Button', 'AreaAbilityPlan3Button'])
FEATURES.extend(['ButtonHuanjingGo', 'ButtonBlessHuanjingQuickPlay', 'ButtonHuanjingConfirm',
                 'ButtonHuanjingCancel', 'ButtonJihuaInnerGo', 'ButtonJihuaNumConfirm',
                 'ButtonJihuaFinallyConfirm', 'ButtonMinigameQuit', 'ButtonMinigameRetry',
                 'ButtonMinigameRetryOk', 'IconFishingFinish', 'IconFishingStrike',
                 'IconFishingPullLine', 'IconFishingPullLineHome', 'IconFishingReelIn',
                 'IconFishingSkip', 'IconFishingNoFish', 'IconFishingHomeFeature',
                 'IconFishingMiralandFeature', 'IconTalkFeature', 'IconPageLoginFeature', 'IconUILoading',
                 'ButtonExit', 'ButtonExitLogout', 'ButtonMiraCrownQuickReward', 'ButtonMiraCrownRank',
                 'ButtonMiraCrownStartChallenge', 'ButtonMiraCrownNextStep', 'ButtonMiraCrownConfirmMatch',
                 'ButtonMiraCrownSkipAll', 'ButtonMiraCrownAward', 'ButtonMiraCrownRewardGet',
                 'ButtonMiraCrownShop', 'ButtonMiraCrownShopConfirm'])
REGIONS.extend(['AreaZxxyEnergy', 'AreaWeeklyCountText', 'AreaBlessHuanjingLevelsSelect',
                'AreaBlessHuanjingDifficulty3', 'AreaHuanjingJihuaEntrace', 'AreaHuanjingBlessEntrace',
                'AreaHuanjingMonsterEntrace', 'AreaHuanjingBossEntrace', 'AreaTextJihuatai',
                'AreaJihuaTargetSelect', 'AreaJihuaCostSelect', 'AreaFishingIcons', 'AreaFishingDetection',
                'AreaMinigameEscSelect', 'AreaSubAbilityButton', 'AreaLoginOCR', 'AreaExitBackLoginButton',
                'AreaRegisterLoginButton', 'AreaLoginAccountList', 'AreaMiraCrownOverview',
                'AreaMiraCrownEntrance', 'AreaMiraCrownSecondDoor', 'AreaMiraCrownThirdDoor',
                'AreaMiraCrownAutoMatchButton', 'AreaMiraCrownShopItemList', 'AreaBigMapMeteorText'])
REGIONS.extend(['AreaBigMapMaterialTypeSelect', 'AreaBigMapMaterialSelect', 'AreaBigMapMaterialTrackConfirm'])


def nonblack_bbox(image):
    mask = np.max(image[:, :, :3], axis=2) > 15
    ys, xs = np.where(mask)
    if not len(xs):
        raise ValueError('Source annotation has no non-black pixels')
    return [int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]


def main():
    from ok.feature.FeatureSet import generate_templates

    source = ROOT / 'whimbox_app/python-embedded/Lib/site-packages/whimbox/assets'
    index = json.loads((source / 'imgs/imgs_index.json').read_text(encoding='utf-8'))
    authoring = ROOT / 'ok_templates'
    authoring.mkdir(parents=True, exist_ok=True)
    assets = ROOT / 'assets'
    assets.mkdir(exist_ok=True)
    images, categories, annotations = [], [], []
    manifest = {'source': 'local whimbox 3.1.1', 'reference_size': [1920, 1080], 'features': {}, 'regions': {}}

    for number, name in enumerate(FEATURES + REGIONS, 1):
        path = source / Path(index[name]['rel_path'].replace('\\', '/'))
        raw = cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
        if raw is None:
            raise ValueError(f'Unreadable image: {path}')
        original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if name in {'IconPickupFeature', 'IconSetdownFeature', 'IconAbilityInsect', 'IconTalkFeature'}:
            # Supplied pickup is a crop, not a screenshot. Reconstruct an authoring
            # canvas and explicitly search AreaPickup at runtime, not this placement.
            region_name = 'AreaAbilityButton' if name == 'IconAbilityInsect' else 'AreaPickup'
            if name == 'IconAbilityInsect':
                raw = cv2.resize(raw, None, fx=0.73, fy=0.73, interpolation=cv2.INTER_AREA)
            area_path = source / Path(index[region_name]['rel_path'].replace('\\', '/'))
            area = cv2.imdecode(np.frombuffer(area_path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
            x, y, width, height = nonblack_bbox(area)
            x += (width - raw.shape[1]) // 2
            y += (height - raw.shape[0]) // 2
            canvas = np.zeros((1080, 1920, 3), dtype=np.uint8)
            canvas[y:y + raw.shape[0], x:x + raw.shape[1]] = raw
            bbox = [x, y, raw.shape[1], raw.shape[0]]
            raw = canvas
        else:
            if name == 'AreaMiraCrownSecondDoor' and raw.shape[:2] == (1200, 1920):
                # Source uses a 16:10 center anchor: remove 60px from both edges.
                raw = raw[60:1140].copy()
            if raw.shape[:2] != (1080, 1920):
                raise ValueError(f'Unexpected reference resolution for {name}: {raw.shape}')
            bbox = nonblack_bbox(raw)
        filename = f'{name}.png'
        output_path = authoring / filename
        encoded = cv2.imencode('.png', raw)[1].tobytes()
        if output_path.exists() and output_path.read_bytes() != encoded:
            raise ValueError(f'Refusing to replace changed authoring image: {output_path}')
        output_path.write_bytes(encoded)
        category_name = f'box_{name}' if name in REGIONS else name
        images.append({'id': number, 'file_name': filename, 'width': 1920, 'height': 1080})
        categories.append({'id': number, 'name': category_name, 'supercategory': 'whimbox'})
        annotations.append({'id': number, 'image_id': number, 'category_id': number,
                            'bbox': bbox, 'area': bbox[2] * bbox[3], 'iscrowd': 0})
        manifest['regions' if name in REGIONS else 'features'][name] = {
            'bbox': bbox, 'source': path.relative_to(ROOT).as_posix(), 'sha256': original_hash,
            'authoring': output_path.relative_to(ROOT).as_posix(),
            'authoring_sha256': hashlib.sha256(encoded).hexdigest(),
        }

    coco_path = authoring / 'coco_annotations.json'
    data = {'images': images, 'categories': categories, 'annotations': annotations}
    if coco_path.exists():
        existing = json.loads(coco_path.read_text(encoding='utf-8'))
        # Extend the dataset while preserving IDs and unrelated user annotations.
        image_ids = {row['file_name']: row['id'] for row in existing['images']}
        category_ids = {row['name']: row['id'] for row in existing['categories']}
        new_images = {row['id']: row['file_name'] for row in images}
        new_categories = {row['id']: row['name'] for row in categories}
        for row in images:
            if row['file_name'] not in image_ids:
                identity = max(image_ids.values(), default=0) + 1
                image_ids[row['file_name']] = identity
                existing['images'].append({**row, 'id': identity})
        for row in categories:
            if row['name'] not in category_ids:
                identity = max(category_ids.values(), default=0) + 1
                category_ids[row['name']] = identity
                existing['categories'].append({**row, 'id': identity})
        for row in annotations:
            image_id = image_ids[new_images[row['image_id']]]
            category_id = category_ids[new_categories[row['category_id']]]
            previous = next((a for a in existing['annotations'] if a['image_id'] == image_id and a['category_id'] == category_id), None)
            if previous is not None and previous['bbox'] != row['bbox']:
                raise ValueError('Existing annotation was edited; export it through Template tab instead')
            if previous is None:
                identity = max((a['id'] for a in existing['annotations']), default=0) + 1
                existing['annotations'].append({**row, 'id': identity, 'image_id': image_id, 'category_id': category_id})
        data = existing
    coco_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    generate_templates(str(coco_path), str(assets / 'templates'), str(authoring), generate_label_enmu=None)
    (assets / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    from nuannuan.routes.ability import ABILITY_ICONS, JUMP_ICONS
    icon_folder = assets / 'ability_icons'
    icon_folder.mkdir(exist_ok=True)
    for name in [*ABILITY_ICONS.values(), *JUMP_ICONS.values(), 'IconAbilityMachineInfuse', 'IconAbilityMachineExtract']:
        path = source / Path(index[name]['rel_path'].replace('\\', '/'))
        target = icon_folder / f'{name}.png'
        if target.exists() and target.read_bytes() != path.read_bytes():
            raise ValueError(f'Refusing to overwrite edited ability icon: {target}')
        shutil.copy2(path, target)
        manifest.setdefault('ability_icons', {})[name] = {'source': path.relative_to(ROOT).as_posix(),
                                                       'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    (assets / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

    # UI sprites are searched within a verified page rather than at fixed positions.
    sprite_folder = assets/'game_icons'
    sprite_folder.mkdir(exist_ok=True)
    for name, source_name in {'IconMaterialTypeAnimal':'IconMaterialTypeAnimal',
                              'IconMaterialTypeInsect':'IconMaterialTypeInsect',
                              'StarCrystal':'T_UI_map_img_icon_star_02'}.items():
        path=source/Path(index[source_name]['rel_path'].replace('\\','/'))
        target=sprite_folder/f'{name}.png'
        if target.exists() and target.read_bytes()!=path.read_bytes():
            raise ValueError(f'Refusing to overwrite edited tracking icon: {target}')
        shutil.copy2(path,target)
        manifest.setdefault('game_icons',{})[name]={'local_icon':target.relative_to(ROOT).as_posix(),
                                                  'source':path.relative_to(ROOT).as_posix(),
                                                  'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    (assets/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')

    # Material icons are individual UI sprites, separate from position-bound templates.
    material_data = json.loads((source/'material.json').read_text(encoding='utf-8'))
    material_folder = assets/'material_icons'
    material_folder.mkdir(exist_ok=True)
    for material, info in material_data.items():
        path = source/Path(index[info['game_img']]['rel_path'].replace('\\', '/'))
        destination = material_folder/f'{info["game_img"]}.png'
        if destination.exists() and destination.read_bytes() != path.read_bytes():
            raise ValueError(f'Refusing to overwrite edited material icon: {destination}')
        shutil.copy2(path, destination)
        info.update({'local_icon': destination.relative_to(ROOT).as_posix(),
                     'source': path.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    (assets/'materials.json').write_text(json.dumps(material_data, ensure_ascii=False, indent=2), encoding='utf-8')
    source_options = json.loads((source/'setting_options.json').read_text(encoding='utf-8'))
    game_options = {key: source_options[key] for key in ['jihua_target', 'bless_target', 'monster_target',
                                                        'realm_target', 'mira_crown_award_target']}
    (assets/'setting_options.json').write_text(json.dumps(game_options, ensure_ascii=False, indent=2), encoding='utf-8')

    # Reuse already supplied OCR models; runtime has no model download step.
    models_source = source.parent.parent / 'rapidocr/models'
    model_folder = assets / 'ocr'
    model_folder.mkdir(exist_ok=True)
    for name in ['ch_PP-OCRv5_mobile_det.onnx', 'ch_PP-OCRv5_rec_mobile_infer.onnx',
                 'ch_ppocr_mobile_v2.0_cls_infer.onnx', 'ppocrv5_dict.txt', 'FZYTK.TTF']:
        src = models_source / name
        dest = model_folder / name
        if dest.exists() and dest.read_bytes() != src.read_bytes():
            raise ValueError(f'Refusing to replace changed OCR model: {dest}')
        shutil.copy2(src, dest)
        manifest.setdefault('ocr', {})[name] = {'source': src.relative_to(ROOT).as_posix(),
                                                'sha256': hashlib.sha256(src.read_bytes()).hexdigest()}
    (assets / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    license_dir = ROOT / 'licenses'
    license_dir.mkdir(exist_ok=True)
    shutil.copy2(source.parent.parent / 'whimbox-3.1.1.dist-info/licenses/LICENSE', license_dir / 'whimbox-GPL-3.0.txt')
    shutil.copy2(ROOT / 'ok-script/LICENSE.txt', license_dir / 'ok-script-LICENSE.txt')
    print(f'Imported {len(FEATURES)} features, {len(REGIONS)} regions and local OCR resources.')


if __name__ == '__main__':
    main()

"""Behavioral checks plus real model parity; four boxes are not doubles evidence."""
import json
from pathlib import Path

import numpy as np
import pytest
import torch

from adapters import HERE, ROOT, COCO17, load, padded_boxes
from panel import select, R
from run import ranges, joint_features, make_clips, metrics
from app.services.tracking.video_io import iter_frames


@pytest.fixture(scope='module')
def frame():
    panel = json.loads((HERE / 'panels/small.json').read_text())
    d = R.MatchFrames('041')
    fid = panel['events'][0]['frame']
    _, image = next(iter_frames(str(ROOT / 'research/shuttleset/videos/041.mp4'), start=fid, stop=fid + 1))
    boxes = d.data['player_box'][d.indices[fid]].copy()
    assert np.isfinite(boxes).all()
    return image, boxes


def test_selection_is_independent_of_input_order_and_preserves_no_pose_label():
    rows = [dict(id=str(i), **{'class': (i % 3) + 1}, no_pose=(i == 1)) for i in range(20)]
    assert select(rows, 2) == select(rows[::-1], 2)
    assert len(select(rows, 0)) == 20


def test_ranges_never_relabel_frames_across_gaps():
    assert ranges([12, 8, 9, 12, 15]) == [(8, 10), (12, 13), (15, 16)]
    assert ranges([]) == []


def test_abstention_is_in_denominator_and_side_type_errors_are_separate():
    rows = [dict(label=1, prediction=0, abstain_reason='missing_pose_coverage'),
            dict(label=1, prediction=13, abstain_reason=None),
            dict(label=2, prediction=2, abstain_reason=None)]
    m = metrics(rows)
    assert m['exact_accuracy'] == 1 / 3 and m['macro_recall'] == .5
    assert m['type_accuracy'] == 2 / 3 and m['side_accuracy'] == 1 / 3
    assert m['classified'] == 2 and m['abstentions'] == {'missing_pose_coverage': 1}


def test_missing_far_does_not_move_near_into_far_slot():
    kp = np.ones((3, 2, 17, 3), np.float32)
    box = np.broadcast_to(np.array([0, 0, 10, 20], np.float32), (3, 2, 4)).copy()
    kp[0, 0] = np.nan
    kp[1, 1] = np.nan
    kp[2] = np.nan
    j, cov, res = joint_features(kp, box)
    assert not j[0].any() and not j[1, 1].any() and j[1, 0].any()
    assert cov.tolist() == [True, True, False] and not res.any()
    with pytest.raises(ValueError):
        joint_features(np.ones((3, 4, 17, 3)), np.ones((3, 4, 4)))


def test_missing_windows_are_not_removed_from_selected_rows():
    events = [dict(id='a', frame=10, **{'class': 1}), dict(id='b', frame=20, **{'class': 2})]
    arr = np.ones((2, 2, 2), np.float32)
    clips, locs, rows = make_clips(events, [[10], [20, 21]], {10: 0, 20: 0, 21: 1},
                                 np.zeros((2, 2, 17, 2)), np.array([True, False]),
                                 np.array([True, True]), arr, np.ones((2, 2)))
    assert not clips and not locs and len(rows) == 2
    assert [r['abstain_reason'] for r in rows] == ['missing_window', 'missing_pose_coverage']


@pytest.mark.parametrize('boxes', [[[np.nan, 0, 10, 10]], [[10, 0, 0, 10]], [[1000, 0, 1100, 10]]])
def test_bad_boxes_fail(boxes):
    with pytest.raises(ValueError):
        padded_boxes(np.zeros((100, 100, 3), np.uint8), boxes)


@pytest.mark.parametrize('name', ['rtmpose_m', 'rtmpose_x', 'vitpose_plus_base'])
def test_real_model_reference_and_four_box_order(name, frame):
    image, boxes = frame
    model = load(name, threads=2)
    # Four distinct crops of a two-person frame: interface/permutation test only.
    four = np.concatenate((boxes, boxes + np.array([1, 2, -1, -2], np.float32)))
    actual = model.estimate(image, four)
    h, w = image.shape[:2]
    padded = four.copy()
    margin = .1 * (four[:, 2:] - four[:, :2])
    padded[:, :2] = np.maximum(four[:, :2] - margin, 0)
    padded[:, 2:] = np.minimum(four[:, 2:] + margin, [w - 1, h - 1])
    if name.startswith('rtmpose'):
        from rtmlib import RTMPose
        reference = RTMPose(str(model.path), model_input_size=model.size, backend='onnxruntime', device='cpu')
        rgb_or_bgr = image[:, :, ::-1].copy() if name == 'rtmpose_x' else image
        kp, sc = reference(rgb_or_bgr, bboxes=padded)
        expected = np.concatenate((kp, sc[..., None]), -1)
    else:
        expected = []
        # HF-native single-person calls independently construct XYWH and select COCO expert.
        for x1, y1, x2, y2 in padded:
            xywh = [[[float(x1), float(y1), float(x2 - x1), float(y2 - y1)]]]
            inputs = model.processor(image[:, :, ::-1].copy(), boxes=xywh, return_tensors='pt')
            with torch.inference_mode():
                output = model.model(**inputs, dataset_index=torch.tensor([0]))
            row = model.processor.post_process_pose_estimation(output, boxes=xywh)[0][0]
            expected.append(np.column_stack((row['keypoints'].numpy(), row['scores'].numpy())))
        expected = np.stack(expected)
    np.testing.assert_allclose(actual, expected, rtol=0, atol=.03)
    order = [3, 1, 0, 2]
    permuted = model.estimate(image, four[order])
    np.testing.assert_allclose(permuted, actual[order], rtol=0, atol=.03)
    assert model.estimate(image, []).shape == (0, 17, 3)
    (HERE / 'checks').mkdir(exist_ok=True)
    (HERE / 'checks' / f'{name}.json').write_text(json.dumps(dict(model=model.info,
        max_reference_error=float(np.abs(actual - expected).max()),
        max_permutation_error=float(np.abs(permuted - actual[order]).max()),
        scope='one real validation frame, four crops; reference integration only, not doubles accuracy'), indent=2) + '\n')

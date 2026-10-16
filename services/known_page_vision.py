"""013-V01 local-only geometry and ink reader. No OCR/network/model calls.

Shape scores are distances, not calibrated probabilities. Until real handwriting
validation exists every candidate is held for human confirmation.
"""
import hashlib
from pathlib import Path
from typing import Protocol
import re
import cv2
import numpy as np


class PageMatcher(Protocol):
    def match(self, image, candidates): ...


class HandwrittenChoiceReader(Protocol):
    def read(self, reference, aligned, bbox, multi=False): ...


def load_image(path):
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    if image is None or image.size > 30_000_000:
        raise ValueError("Invalid image or image exceeds 30 megapixels")
    return image


def png(image):
    ok, data = cv2.imencode('.png', image)
    if not ok:
        raise ValueError('PNG encoding failed')
    return data.tobytes()


def normalize_paper_illumination(image):
    """Remove slow lighting gradients before fixed ink thresholds, not ink itself."""
    background=cv2.GaussianBlur(image,(0,0),25)
    return cv2.divide(image,np.maximum(background,1),scale=245)


def expanded_answer_roi(placement, shape):
    """Bounded context for over-bracket strokes; never include printed option rows.

    This is geometry only. No label, key or handwriting calibration is input.
    Writing beyond this safe area remains a refusal, not a guessed answer.
    """
    x1,y1,x2,y2=map(int,placement.answer_bracket_bbox)
    width,height=x2-x1,y2-y1
    q=placement.question_bbox
    option_top=placement.options_bbox[1]
    return [max(q[0],x1-round(width*.15)),max(q[1],y1-round(height*.5)),
            min(q[2],shape[1],x2+round(width*.15)),min(q[3],shape[0],option_top,y2+round(height*.75))]


def teacher_registration(original, reference, original_points, reference_points, placements):
    """Explicit human correspondence fallback; NOT automatic page-match evidence."""
    src=np.asarray(original_points,dtype=np.float32)
    dst=np.asarray(reference_points,dtype=np.float32)
    if src.shape!=(4,2) or dst.shape!=(4,2) or not np.isfinite(src).all() or not np.isfinite(dst).all():
        raise ValueError('Exactly four finite corresponding points are required')
    for points,image in ((src,original),(dst,reference)):
        if (points<0).any() or (points[:,0]>=image.shape[1]).any() or (points[:,1]>=image.shape[0]).any():
            raise ValueError('Corresponding point outside page')
        if not cv2.isContourConvex(points) or cv2.contourArea(points,oriented=True)<=image.size*.04:
            raise ValueError('Correspondences must be clockwise, broad and non-mirrored')
    h=cv2.getPerspectiveTransform(src,dst)
    coarse=h.copy()
    # Human-supplied landmarks disambiguate repeated printed rows. Refine only
    # feature pairs already within 20 reference pixels of that explicit mapping.
    detector=cv2.SIFT_create(nfeatures=5000)
    ok,od=detector.detectAndCompute(original,None)
    rk,rd=detector.detectAndCompute(reference,None)
    refinement=None
    if od is not None and rd is not None:
        pairs=cv2.BFMatcher().knnMatch(od,rd,k=2)
        near=[]
        for pair in pairs:
            if len(pair)!=2:continue
            a,b=pair
            if a.distance>=.65*b.distance:continue
            projected=cv2.perspectiveTransform(np.float32([[ok[a.queryIdx].pt]]),coarse)[0,0]
            if np.linalg.norm(projected-np.array(rk[a.trainIdx].pt))<20:near.append(a)
        if len(near)>=20:
            refined,mask=cv2.findHomography(np.float32([ok[a.queryIdx].pt for a in near]),np.float32([rk[a.trainIdx].pt for a in near]),cv2.RANSAC,2.5)
            if refined is not None and mask is not None and int(mask.sum())>=20 and float(mask.mean())>=.65:
                shift=float(np.max(np.linalg.norm(cv2.perspectiveTransform(src[None],refined)[0]-dst,axis=1)))
                if shift<20:
                    h=refined
                    refinement={'near_pairs':len(near),'inliers':int(mask.sum()),'inlier_ratio':float(mask.mean()),'max_anchor_shift':shift}
    inv=np.linalg.inv(h)
    region=np.zeros(reference.shape,np.uint8)
    for p in placements:
        x1,y1,x2,y2=p.question_bbox
        pixels=cv2.findNonZero((reference[y1:y2,x1:x2]<190).astype('uint8'))
        if pixels is None:raise ValueError('Reference question contains no printed content')
        px,py,pw,ph=cv2.boundingRect(pixels)
        # Empty paper margins are not required evidence; every printed question
        # and its registered answer area must still be inside the real photo.
        x2=min(x2,max(x1+px+pw+6,p.answer_bracket_bbox[2]+6))
        region[y1:y2,x1:x2]=1
        projected=cv2.perspectiveTransform(np.float32([[[x1,y1],[x2,y1],[x2,y2],[x1,y2]]]),inv)[0]
        if not cv2.isContourConvex(projected) or (projected<0).any() or (projected[:,0]>=original.shape[1]).any() or (projected[:,1]>=original.shape[0]).any():
            raise ValueError('A mapped question is outside original photo; retake required')
    aligned=normalize_paper_illumination(cv2.warpPerspective(original,h,(reference.shape[1],reference.shape[0]),borderValue=255))
    printed=(reference<160)&(region>0)
    recall=float(np.mean(cv2.dilate((aligned<185).astype('uint8'),np.ones((3,3),np.uint8))[printed])) if printed.any() else 0
    background=(reference>220)&(region>0)
    clear=float(np.mean(aligned[background]>185)) if background.any() else 0
    if clear<.85:
        raise ValueError('Background obscured or dark; retake required')
    if recall<.85:
        raise ValueError(f'Printed background mismatch ({recall:.4f}); check correspondence or retake')
    return aligned,{'method':'TEACHER_CORRESPONDENCE','automatic_match':False,'homography':h.tolist(),
                    'original_points':src.tolist(),'reference_points':dst.tolist(),'printed_recall':recall,
                    'background_clear_rate':clear,'coarse_homography':coarse.tolist(),'guided_refinement':refinement}


class LocalPageMatcher:
    """Allowed candidates supplied by server; never searches another variant."""
    def match(self, image, candidates):
        rejected=[]
        uid, _, _ = cv2.QRCodeDetector().detectAndDecode(image)
        if uid and uid not in {p.page_uid for p in candidates}:
            return None, None, {'reason': 'FOREIGN_PAGE_MARKER'}
        orb = cv2.ORB_create(nfeatures=3500)
        kp, desc = orb.detectAndCompute(image, None)
        if desc is None or cv2.Laplacian(image, cv2.CV_64F).var() < 12:
            return None, None, {'reason': 'BLURRED_OR_NO_FEATURES'}
        results = []
        for page in candidates:
            if uid and uid != page.page_uid:
                continue
            if getattr(page,'image_sha256',None) and hashlib.sha256(Path(page.image_locator).read_bytes()).hexdigest()!=page.image_sha256:
                continue
            ref = load_image(page.image_locator)
            rk, rd = orb.detectAndCompute(ref, None)
            if rd is None:
                continue
            pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(desc, rd, k=2)
            good = [a for pair in pairs if len(pair) == 2 for a, b in [pair] if a.distance < .65*b.distance]
            if len(good) < 20:
                rejected.append({'page':page.id,'gate':'FEATURE_COUNT','matches':len(good)})
                continue
            src = np.float32([kp[m.queryIdx].pt for m in good])
            dst = np.float32([rk[m.trainIdx].pt for m in good])
            h, mask = cv2.findHomography(src, dst, cv2.RANSAC, 2.5)
            if h is None or mask is None or not np.isfinite(h).all():
                continue
            inside = mask.ravel().astype(bool)
            count, ratio = int(inside.sum()), float(inside.mean())
            coverage = float(cv2.contourArea(cv2.convexHull(dst[inside])) / ref.size)
            if count < 20 or ratio < .65 or coverage < .08:
                rejected.append({'page':page.id,'gate':'RANSAC_OR_COVERAGE','inliers':count,'ratio':ratio,'coverage':coverage})
                continue
            # Reject mirroring, extreme perspective and missing page edges.
            corners = np.float32([[0, 0], [page.width-1, 0], [page.width-1, page.height-1], [0, page.height-1]])
            try:
                projected = cv2.perspectiveTransform(corners[None], np.linalg.inv(h))[0]
            except np.linalg.LinAlgError:
                continue
            area = cv2.contourArea(projected, oriented=True)
            ih, iw = image.shape
            if area <= 0 or not cv2.isContourConvex(projected) or np.any(projected < -8) or np.any(projected[:, 0] > iw+8) or np.any(projected[:, 1] > ih+8):
                rejected.append({'page':page.id,'gate':'MIRROR_OR_MISSING_EDGE','projected':projected.tolist(),'area':area})
                continue
            aligned = normalize_paper_illumination(cv2.warpPerspective(image, h, (page.width, page.height), borderValue=255))
            # Exclude writing but demand broad printed-background agreement.
            ink = ref < 160
            printed_recall = float(np.mean(cv2.dilate((aligned < 185).astype('uint8'), np.ones((3,3),np.uint8))[ink])) if ink.any() else 0
            if printed_recall < .85:
                rejected.append({'page':page.id,'gate':'PRINT_MISMATCH','printed_recall':printed_recall})
                continue
            ev = {'method': 'QR+ORB' if uid else 'ORB', 'inliers': count, 'inlier_ratio': ratio,
                  'coverage': coverage, 'printed_recall': printed_recall, 'homography': h.tolist()}
            results.append((count, page, aligned, ev))
        results.sort(key=lambda x: x[0], reverse=True)
        if not results:
            return None, None, {'reason': 'UNMATCHED_LAYOUT','rejections':rejected}
        if len(results) > 1 and results[1][0] >= results[0][0] * .8:
            return None, None, {'reason': 'AMBIGUOUS_PAGE'}
        _, page, aligned, ev = results[0]
        return page, aligned, ev


# Original geometric pen-stroke exemplars, not font glyphs or expected answers.
STROKES = {
    'A': [[(5,28),(16,3),(28,28)], [(10,18),(23,18)]],
    'B': [[(6,28),(6,3),(18,3),(26,7),(26,12),(18,16),(6,16)], [(18,16),(27,20),(27,25),(20,28),(6,28)]],
    'C': [[(27,7),(21,3),(11,3),(5,9),(4,21),(10,28),(22,28),(28,24)]],
    'D': [[(6,28),(6,3),(17,3),(25,8),(28,15),(26,23),(18,28),(6,28)]],
}


def normalize_ink(mask):
    points = cv2.findNonZero(mask)
    if points is None:
        return np.zeros((40,40), np.uint8)
    x,y,w,h = cv2.boundingRect(points)
    scale = 30/max(w,h)
    resized = cv2.resize(mask[y:y+h,x:x+w], (max(1,round(w*scale)),max(1,round(h*scale))))
    out = np.zeros((40,40),np.uint8)
    rh,rw = resized.shape
    out[(40-rh)//2:(40-rh)//2+rh,(40-rw)//2:(40-rw)//2+rw] = resized
    return (out > 100).astype(np.uint8)*255


class LocalStrokeReader:
    version = 'opencv-stroke-distance-v1-UNCALIBRATED'

    def __init__(self):
        self.templates = []
        for label, strokes in STROKES.items():
            for thickness in (1,2,3):
                canvas = np.zeros((32,32),np.uint8)
                for stroke in strokes:
                    cv2.polylines(canvas,[np.array(stroke,np.int32)],False,255,thickness,cv2.LINE_AA)
                self.templates.append((label, normalize_ink(canvas)))

    def read(self, reference, aligned, bbox, multi=False):
        x1,y1,x2,y2 = map(int,bbox)
        ref, crop = reference[y1:y2,x1:x2], aligned[y1:y2,x1:x2]
        background = cv2.dilate((ref < 190).astype(np.uint8), np.ones((3,3),np.uint8))
        ink = ((crop < 160) & (background == 0)).astype(np.uint8)*255
        count, labels, stats, _ = cv2.connectedComponentsWithStats(ink)
        for i in range(1,count):
            if stats[i,cv2.CC_STAT_AREA] < 3:
                ink[labels == i] = 0
        pixels = int(np.count_nonzero(ink))
        base = {'symbol': 'BLANK' if pixels < 8 else 'UNCERTAIN', 'status':'HOLD_REVIEW',
                'reason':'BLANK' if pixels < 8 else 'UNCALIBRATED_HANDWRITING',
                'score':0.0, 'reader':self.version, 'ink_pixels':pixels, 'candidates':[]}
        if pixels < 8:
            return base, crop, ink
        # Never infer ink outside the permitted stem bracket region.
        if np.any(ink[:2]) or np.any(ink[-2:]) or np.any(ink[:,:2]) or np.any(ink[:,-2:]):
            base['reason'] = 'INK_TOUCHES_BOUNDARY'
            return base,crop,ink
        columns = (ink > 0).sum(axis=0) > 0
        starts = np.where(np.diff(np.r_[False, columns, False].astype(int)) == 1)[0]
        ends = np.where(np.diff(np.r_[False, columns, False].astype(int)) == -1)[0]
        segments = [(a,b) for a,b in zip(starts,ends) if b-a >= 3]
        if not segments or len(segments) > (4 if multi else 1):
            base['reason'] = 'MULTI_MARK_OR_ERASURE'
            return base,crop,ink
        candidates=[]
        for a,b in segments:
            sample = normalize_ink(ink[:,a:b])
            sample_dist = cv2.distanceTransform(255-sample,cv2.DIST_L2,3)
            scores={}
            for label, prototype in self.templates:
                dist = cv2.distanceTransform(255-prototype,cv2.DIST_L2,3)
                score = float((dist[sample>0].mean()+sample_dist[prototype>0].mean())/2)
                scores[label]=min(scores.get(label,999),score)
            ordered=sorted(scores.items(),key=lambda x:x[1])
            candidates.append({'symbol':ordered[0][0], 'distance':ordered[0][1], 'margin':ordered[1][1]-ordered[0][1]})
        base['candidates']=candidates
        if all(c['distance'] < 1.8 and c['margin'] > .25 for c in candidates):
            symbols=[c['symbol'] for c in candidates]
            if len(set(symbols)) == len(symbols):
                base['symbol']=''.join(sorted(symbols))
                base['score']=round(max(0,1-max(c['distance'] for c in candidates)/4),4)
        return base,crop,ink


class AnswerKeyGrader:
    @staticmethod
    def normalize(value, multi=False):
        value=(value or '').strip().upper()
        if not re.fullmatch(r'[ABCD]{1,4}', value) or len(set(value)) != len(value):
            return None
        if not multi and len(value) != 1:
            return None
        return ''.join(sorted(value))

    def grade(self, answer, key, max_score, multi=False):
        if not 0 < float(max_score) <= 999.99:
            raise ValueError('HOLD_REVIEW: score outside existing grading storage bounds')
        key=self.normalize(key,multi)
        value='' if answer == 'BLANK' else self.normalize(answer,multi)
        if not key or value is None:
            raise ValueError('HOLD_REVIEW: invalid answer or unconfirmed key')
        correct=value == key
        return {'result':'correct' if correct else 'wrong', 'score':float(max_score) if correct else 0.0, 'correct_answer':key}

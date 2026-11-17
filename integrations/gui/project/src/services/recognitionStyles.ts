import palette from '../../../../../backend/vision/annotation_palette.json';
import type { Detection, FaceVerifyResult } from '@/types/contracts';

export const recognitionPalette = palette;
export type FaceAnnotation = Pick<FaceVerifyResult, 'identity_matched' | 'liveness_status' | 'access_granted'> & {
  bbox: [number, number, number, number];
};

export function objectStyle(detection: Pick<Detection, 'model'>) {
  return palette[detection.model === 'general' || detection.model === 'custom' ? detection.model : 'unknown'];
}

export function faceStyle(face: Omit<FaceAnnotation, 'bbox'>, source: 'camera' | 'upload' = 'camera') {
  if (face.identity_matched === false) return palette.face_unauthorized;
  if (face.identity_matched !== true) return palette.unknown;
  const status = source === 'upload' ? 'unavailable' : face.liveness_status;
  if (status === 'passed') return face.access_granted === true ? palette.face_granted : palette.face_live;
  if (status === 'pending') return palette.face_pending;
  if (status === 'timeout' || status === 'failed') return palette.face_failed;
  if (status === 'unavailable' || status === 'not_applicable') return palette.face_unavailable;
  return palette.unknown;
}

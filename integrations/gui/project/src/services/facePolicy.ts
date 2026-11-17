import type { FaceVerifyResult, RecognitionSource } from '@/types/contracts';
type FaceState = Pick<FaceVerifyResult, 'matched' | 'access_granted' | 'liveness_status' | 'identity_recheck' | 'verification_remaining_seconds'>;
export function faceAccessLabel(face: FaceState, source: RecognitionSource): string {
  if (source !== 'camera') return face.matched ? '身份匹配，但静态照片没有通行资格' : '身份未匹配，静态照片没有通行资格';
  if (face.liveness_status === 'timeout') return '验证超时，请重新面对摄像头';
  if (!face.matched) return face.identity_recheck && face.liveness_status === 'pending' ? '活体验证中' : '未匹配授权人员';
  if (face.access_granted === true && face.liveness_status === 'passed') return '验证通过，门状态以设备反馈为准';
  if (face.liveness_status === 'unavailable') return '活体服务不可用，不予通行';
  return '活体验证中';
}

import type { FaceVerifyResult, RecognitionSource } from '@/types/contracts';
type FaceState = Pick<FaceVerifyResult, 'matched' | 'access_granted' | 'liveness_status'>;
export function faceAccessLabel(face: FaceState, source: RecognitionSource): string {
  if (source !== 'camera') return '静态照片不予通行';
  if (!face.matched) return '未匹配授权人员';
  if (face.access_granted === true && face.liveness_status === 'passed') return '验证通过，门状态以设备反馈为准';
  if (face.liveness_status === 'timeout') return '验证超时，请重新面对摄像头';
  if (face.liveness_status === 'unavailable') return '活体服务不可用，不予通行';
  return '等待当前人员眨眼';
}

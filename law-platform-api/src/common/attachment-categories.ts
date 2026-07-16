/**
 * MinIO 业务存储分类（与 MinioService.CATEGORIES 对齐）。
 * 决定 object_key 的路径段：{prefix}/{y}/{m}/{no}/{category}/...
 * 与「案件材料业务分类」(case_material.material_type) 是两个独立维度。
 */
export const ATTACHMENT_CATEGORIES = [
  'evidence',
  'contract',
  'pleading',
  'court',
  'progress',
  'consultation',
  'invoice',
  'agreement',
  'other',
] as const;

export type AttachmentCategory = (typeof ATTACHMENT_CATEGORIES)[number];

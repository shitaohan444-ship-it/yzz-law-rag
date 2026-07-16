import { IsIn, IsNotEmpty, IsString } from 'class-validator';
import { ATTACHMENT_CATEGORIES } from '../../../common/attachment-categories';

/**
 * 后补/替换材料文件 DTO（multipart 文本字段，文件本身走 @UploadedFile）。
 */
export class ReplaceFileDto {
  @IsIn(ATTACHMENT_CATEGORIES)
  category: string; // MinIO 存储分类（决定 object_key 路径段）

  @IsString()
  @IsNotEmpty()
  uploadedBy: string; // 操作人员工 ID —— @TODO 鉴权
}

import { Module } from '@nestjs/common';
import { AttachmentModule } from '../attachments/attachment.module';
import { CaseMaterialService } from './case-material.service';
import { CaseMaterialsController } from './case-materials.controller';

@Module({
  imports: [AttachmentModule], // 注入 AttachmentService
  controllers: [CaseMaterialsController],
  providers: [CaseMaterialService],
  exports: [CaseMaterialService],
})
export class CaseMaterialsModule {}

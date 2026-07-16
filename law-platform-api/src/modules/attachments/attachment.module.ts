import { Module } from '@nestjs/common';
import { AttachmentService } from './attachment.service';
import { AttachmentsController } from './attachments.controller';

@Module({
  controllers: [AttachmentsController],
  providers: [AttachmentService],
  exports: [AttachmentService],
})
export class AttachmentModule {}

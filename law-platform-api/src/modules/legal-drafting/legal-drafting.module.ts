import { Module } from '@nestjs/common';
import {
  LegalDraftingController,
  LegalDraftingWorkerController,
} from './legal-drafting.controller';
import { LegalDraftingService } from './legal-drafting.service';
import { AttachmentModule } from '../attachments/attachment.module';

@Module({
  imports: [AttachmentModule],
  controllers: [LegalDraftingController, LegalDraftingWorkerController],
  providers: [LegalDraftingService],
  exports: [LegalDraftingService],
})
export class LegalDraftingModule {}

import { Module } from '@nestjs/common';
import { RagModule } from '../rag/rag.module';
import { KnowledgeDocumentsController } from './knowledge-documents.controller';
import { KnowledgeDocumentsService } from './knowledge-documents.service';

@Module({
  imports: [RagModule],
  controllers: [KnowledgeDocumentsController],
  providers: [KnowledgeDocumentsService],
  exports: [KnowledgeDocumentsService],
})
export class KnowledgeDocumentsModule {}

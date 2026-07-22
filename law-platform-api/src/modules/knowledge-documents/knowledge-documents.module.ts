import { Module } from '@nestjs/common';
import { RagModule } from '../rag/rag.module';
import { KnowledgeDocumentsController } from './knowledge-documents.controller';
import { KnowledgeDocumentsService } from './knowledge-documents.service';
import { KnowledgeCategoriesController } from './knowledge-categories.controller';
import { KnowledgeCategoriesService } from './knowledge-categories.service';

@Module({
  imports: [RagModule],
  controllers: [KnowledgeDocumentsController, KnowledgeCategoriesController],
  providers: [KnowledgeDocumentsService, KnowledgeCategoriesService],
  exports: [KnowledgeDocumentsService, KnowledgeCategoriesService],
})
export class KnowledgeDocumentsModule {}

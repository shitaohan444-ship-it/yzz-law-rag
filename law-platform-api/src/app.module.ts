import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { envValidationSchema } from './core/config/env.validation';
import { PrismaModule } from './core/prisma/prisma.module';
import { MinioModule } from './core/minio/minio.module';
import { AttachmentModule } from './modules/attachments/attachment.module';
import { CaseMaterialsModule } from './modules/case-materials/case-materials.module';
import { RagModule } from './modules/rag/rag.module';
import { KnowledgeDocumentsModule } from './modules/knowledge-documents/knowledge-documents.module';
import { LegalDraftingModule } from './modules/legal-drafting/legal-drafting.module';
import { DraftingLiteModule } from './modules/drafting-lite/drafting-lite.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      validationSchema: envValidationSchema,
      validationOptions: { abortEarly: false },
    }),
    PrismaModule,
    MinioModule,
    AttachmentModule,
    CaseMaterialsModule,
    RagModule,
    KnowledgeDocumentsModule,
    LegalDraftingModule,
    DraftingLiteModule,
  ],
})
export class AppModule {}

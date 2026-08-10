import { Module } from '@nestjs/common';
import { DraftingLiteController } from './drafting-lite.controller';
import { DraftingLiteService } from './drafting-lite.service';

@Module({
  controllers: [DraftingLiteController],
  providers: [DraftingLiteService],
})
export class DraftingLiteModule {}

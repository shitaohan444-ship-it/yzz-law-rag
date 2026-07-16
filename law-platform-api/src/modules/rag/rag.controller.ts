import { Body, Controller, HttpCode, HttpStatus, Post } from '@nestjs/common';
import { ChatRagDto } from './dto/chat-rag.dto';
import { SearchRagDto } from './dto/search-rag.dto';
import { RagService } from './rag.service';

@Controller('api/rag')
export class RagController {
  constructor(private readonly rag: RagService) {}

  @Post('search')
  @HttpCode(HttpStatus.OK)
  search(@Body() dto: SearchRagDto) {
    return this.rag.search(dto);
  }

  @Post('chat')
  @HttpCode(HttpStatus.OK)
  chat(@Body() dto: ChatRagDto) {
    return this.rag.chat(dto);
  }
}

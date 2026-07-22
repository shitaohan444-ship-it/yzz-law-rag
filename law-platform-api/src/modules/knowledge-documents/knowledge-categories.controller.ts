import {
  Body,
  Controller,
  Delete,
  Get,
  Param,
  Patch,
  Post,
  Query,
} from '@nestjs/common';
import { ParseBigIntPipe } from '../../common/parse-bigint.pipe';
import { CreateKnowledgeCategoryDto } from './dto/create-knowledge-category.dto';
import { UpdateKnowledgeCategoryDto } from './dto/update-knowledge-category.dto';
import { KnowledgeCategoriesService } from './knowledge-categories.service';

@Controller('api/rag/categories')
export class KnowledgeCategoriesController {
  constructor(private readonly categories: KnowledgeCategoriesService) {}

  @Get()
  tree(@Query('include_inactive') includeInactive?: string) {
    return this.categories.tree(includeInactive === 'true');
  }

  @Post()
  create(@Body() dto: CreateKnowledgeCategoryDto) {
    return this.categories.create(dto);
  }

  @Patch(':id')
  update(
    @Param('id', ParseBigIntPipe) id: bigint,
    @Body() dto: UpdateKnowledgeCategoryDto,
  ) {
    return this.categories.update(id, dto);
  }

  @Delete(':id')
  deactivate(@Param('id', ParseBigIntPipe) id: bigint) {
    return this.categories.deactivate(id);
  }
}

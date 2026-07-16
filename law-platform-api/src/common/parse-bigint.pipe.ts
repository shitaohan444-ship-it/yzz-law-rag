import { BadRequestException, Injectable, PipeTransform } from '@nestjs/common';

/**
 * 把字符串/数字路由参数解析为 bigint（NestJS 11 内置只有 ParseIntPipe，装不下 bigint）。
 * 非法值返回 400。
 */
@Injectable()
export class ParseBigIntPipe implements PipeTransform<string, bigint> {
  transform(value: string): bigint {
    try {
      return BigInt(value);
    } catch {
      throw new BadRequestException(`非法的整数参数: ${value}`);
    }
  }
}

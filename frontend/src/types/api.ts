/** 通用 API 相关类型 */

/** 后端错误响应体（形状为暂定契约，接入真实后端前必须核对） */
export interface ApiErrorBody {
  code: string;
  message: string;
  detail?: unknown;
}

/** 前端统一 API 错误 */
export interface ApiError {
  status: number;
  body: ApiErrorBody;
}

/** 列表查询参数 */
export interface PageQuery {
  search?: string;
  status?: string;
  page?: number;
  page_size?: number;
}
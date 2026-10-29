export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
export type DataRecord = Record<string, JsonValue>;
export interface DataField { name: string; label: string; type: "string" | "decimal" | "date" | "boolean" | "enum"; required: boolean; options: string[]; default: string | number | boolean | null }
export interface DataCatalog { resources: Record<string, {label: string; fields: DataField[]}>; currency: string; max_import_rows: number; max_upload_bytes: number }
export interface DataPage { items: DataRecord[]; total?: number; limit: number; offset: number }
export interface ImportPreview { id: string; business_id: string; resource: string; currency: string; filename: string; status: "preview" | "validated" | "committed"; columns: string[]; row_count: number; preview: DataRecord[]; mapping: Record<string,string>; transformed_preview: DataRecord[]; errors: {row:number; field:string; message:string}[]; error_count: number; valid_count: number; imported_count: number; is_demo: boolean; updated_at: string }
export interface DashboardData {
  business_id: string; currency: string; timezone: string; start_date: string; end_date: string; calculation_type: "calculated_historical";
  metrics: {revenue:string; cogs:string|null; gross_profit:string|null; gross_margin_pct:string|null; recorded_expenses:string; operating_profit:string|null; average_order_value:string|null; paid_orders:number};
  expenses_complete:boolean; missing_cost_lines:number; active_customers:number;
  retention:{eligible:number;retained:number;percentage:string|null};
  inventory:null|{value:string|null;valuation:string;as_of:string;stocked_products:number;zero_stock_products:number};
  counts:Record<string,number>; demo_records:number; labels:Record<string,string>;
  trend:{date:string;revenue:string;expenses:string}[]; data_updated_at:string|null; calculated_at:string; methodology:string[];
}

export function displayMoney(value: string|null, currency: string): string {
  if (value === null) return "Incomplete";
  const [whole,fraction] = value.split(".");
  return `${currency} ${whole.replace(/\B(?=(\d{3})+(?!\d))/g,",")}${fraction === undefined ? "" : "."+fraction}`;
}
export function cellText(value: JsonValue | undefined): string {
  return value === null || value === undefined ? "—" : typeof value === "object" ? JSON.stringify(value) : String(value);
}

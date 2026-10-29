import type { DataField } from "@/lib/data-types";

export function DataFields({fields}: {fields:DataField[]}) {
  return <div className="form-grid">{fields.map(field => <label key={field.name}>{field.label}{field.required ? " *" : ""}{field.type === "boolean" ? <input name={field.name} type="checkbox" defaultChecked={Boolean(field.default)}/> : field.type === "enum" ? <select name={field.name} defaultValue={String(field.default ?? field.options[0])}>{field.options.map(value => <option key={value} value={value}>{value}</option>)}</select> : <input name={field.name} required={field.required} type={field.type === "decimal" ? "number" : field.type === "date" ? "date" : field.name === "email" ? "email" : "text"} step={field.type === "decimal" ? "any" : undefined} defaultValue={field.default === null ? "" : String(field.default)} maxLength={field.type === "string" ? 254 : undefined}/>}</label>)}</div>;
}
export function formRecord(form: HTMLFormElement, fields: DataField[]): Record<string,string|boolean> {
  const values=new FormData(form);
  const record:Record<string,string|boolean>={};
  for (const field of fields) {
    if (field.type === "boolean") record[field.name]=values.get(field.name)==="on";
    else {const value=String(values.get(field.name) ?? ""); if(value!=="") record[field.name]=value;}
  }
  return record;
}

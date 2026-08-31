import type { JSONSchema } from '../types'
import { defaultsFromSchema } from '../store'

/**
 * 根据后端返回的 JSON Schema 自动渲染配置表单。
 *
 * 好处：后端加一个节点配置字段，前端什么都不用改。
 * 不需要为每个节点手写一套表单，也不会出现前后端字段对不上。
 */

/** 这些字段内容较长，用多行文本框而不是单行输入 */
const LONG_TEXT_FIELDS = new Set([
  'prompt',
  'expression',
  'body',
  'output_template',
  'description',
  'knowledge_point',
  'answer',
  'rubric',
  'records',
  'requirements',
  'reference',
])

interface SchemaFormProps {
  schema: JSONSchema
  value: unknown
  onChange: (value: unknown) => void
  fieldName?: string
}

export function SchemaForm({ schema, value, onChange, fieldName }: SchemaFormProps) {
  if (schema.enum && schema.enum.length > 0) {
    return (
      <select
        className="field-input"
        value={String(value ?? '')}
        onChange={(e) => onChange(coerce(schema, e.target.value))}
      >
        {schema.enum.map((opt) => (
          <option key={String(opt)} value={String(opt)}>
            {String(opt)}
          </option>
        ))}
      </select>
    )
  }

  switch (schema.type) {
    case 'object':
      return <ObjectEditor schema={schema} value={value} onChange={onChange} />

    case 'array':
      return <ArrayEditor schema={schema} value={value} onChange={onChange} />

    case 'boolean':
      return (
        <label className="field-checkbox">
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => onChange(e.target.checked)}
          />
          <span>{value ? '是' : '否'}</span>
        </label>
      )

    case 'integer':
    case 'number':
      return (
        <input
          className="field-input"
          type="number"
          value={Number(value ?? 0)}
          min={schema.minimum}
          max={schema.maximum}
          onChange={(e) => onChange(e.target.value === '' ? 0 : Number(e.target.value))}
        />
      )

    default:
      return (
        <StringEditor
          schema={schema}
          value={value}
          onChange={onChange}
          multiline={Boolean(fieldName && LONG_TEXT_FIELDS.has(fieldName))}
        />
      )
  }
}

function coerce(schema: JSONSchema, raw: string): unknown {
  if (schema.type === 'integer' || schema.type === 'number') {
    return Number(raw)
  }
  return raw
}

function StringEditor({
  schema,
  value,
  onChange,
  multiline,
}: {
  schema: JSONSchema
  value: unknown
  onChange: (value: unknown) => void
  multiline: boolean
}) {
  const text = String(value ?? '')
  if (multiline) {
    return (
      <textarea
        className="field-input field-textarea"
        rows={4}
        value={text}
        placeholder={schema.description}
        onChange={(e) => onChange(e.target.value)}
      />
    )
  }
  return (
    <input
      className="field-input"
      value={text}
      placeholder={schema.description}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

function ObjectEditor({
  schema,
  value,
  onChange,
}: {
  schema: JSONSchema
  value: unknown
  onChange: (value: unknown) => void
}) {
  const obj = (value ?? {}) as Record<string, unknown>

  // 有明确字段定义：逐字段渲染
  if (schema.properties && Object.keys(schema.properties).length > 0) {
    return (
      <div className="schema-object">
        {Object.entries(schema.properties).map(([key, prop]) => (
          <Field
            key={key}
            name={key}
            schema={prop}
            required={schema.required?.includes(key)}
            value={obj[key]}
            onChange={(next) => onChange({ ...obj, [key]: next })}
          />
        ))}
      </div>
    )
  }

  // 自由键值（例如 start 节点的 inputs）：让用户自己加变量
  return <KeyValueEditor value={obj} onChange={onChange} />
}

function ArrayEditor({
  schema,
  value,
  onChange,
}: {
  schema: JSONSchema
  value: unknown
  onChange: (value: unknown) => void
}) {
  const arr = Array.isArray(value) ? value : []
  const items = schema.items

  const update = (index: number, next: unknown) => {
    const copy = [...arr]
    copy[index] = next
    onChange(copy)
  }
  const remove = (index: number) => onChange(arr.filter((_, i) => i !== index))

  if (items?.type === 'object' && items.properties) {
    return (
      <div className="schema-array">
        {arr.map((item, index) => {
          const record = (item ?? {}) as Record<string, unknown>
          return (
            <div className="array-item" key={index}>
              <div className="array-item-head">
                <span className="array-item-title">
                  {String(record.handle ?? record.label ?? `第 ${index + 1} 项`)}
                </span>
                <button type="button" className="btn-mini" onClick={() => remove(index)}>
                  删除
                </button>
              </div>
              <SchemaForm
                schema={items}
                value={item}
                onChange={(next) => update(index, next)}
              />
            </div>
          )
        })}
        <button
          type="button"
          className="btn-mini"
          onClick={() => onChange([...arr, defaultsFromSchema(items)])}
        >
          + 添加一项
        </button>
      </div>
    )
  }

  return (
    <div className="schema-array">
      {arr.map((item, index) => (
        <div className="array-row" key={index}>
          <input
            className="field-input"
            value={String(item ?? '')}
            onChange={(e) => update(index, e.target.value)}
          />
          <button type="button" className="btn-mini" onClick={() => remove(index)}>
            删除
          </button>
        </div>
      ))}
      <button type="button" className="btn-mini" onClick={() => onChange([...arr, ''])}>
        + 添加一项
      </button>
    </div>
  )
}

function KeyValueEditor({
  value,
  onChange,
}: {
  value: Record<string, unknown>
  onChange: (value: unknown) => void
}) {
  const entries = Object.entries(value)

  const replaceKey = (oldKey: string, newKey: string) => {
    const next: Record<string, unknown> = {}
    for (const [k, v] of entries) {
      next[k === oldKey ? newKey : k] = v
    }
    onChange(next)
  }
  const setValue = (key: string, val: unknown) => {
    onChange({ ...value, [key]: val })
  }
  const remove = (key: string) => {
    const next = { ...value }
    delete next[key]
    onChange(next)
  }

  return (
    <div className="schema-array">
      {entries.map(([key, val]) => (
        <div className="array-row" key={key}>
          <input
            className="field-input field-key"
            value={key}
            placeholder="变量名"
            onChange={(e) => replaceKey(key, e.target.value)}
          />
          <input
            className="field-input"
            value={String(val ?? '')}
            placeholder="默认值"
            onChange={(e) => setValue(key, e.target.value)}
          />
          <button type="button" className="btn-mini" onClick={() => remove(key)}>
            删除
          </button>
        </div>
      ))}
      <button
        type="button"
        className="btn-mini"
        onClick={() => onChange({ ...value, [`var_${entries.length + 1}`]: '' })}
      >
        + 添加变量
      </button>
    </div>
  )
}

function Field({
  name,
  schema,
  value,
  onChange,
  required,
}: {
  name: string
  schema: JSONSchema
  value: unknown
  onChange: (value: unknown) => void
  required?: boolean
}) {
  return (
    <div className="field">
      <label className="field-label">
        {schema.title ?? name}
        {required && <span className="field-required">*</span>}
      </label>
      <SchemaForm schema={schema} value={value} onChange={onChange} fieldName={name} />
    </div>
  )
}

import { LosslessNumber, parse, stringify } from 'lossless-json'

// Keep original numeric literals that JavaScript would round or spell differently.
// Normal game stats stay numbers, so calculations and comparisons still work.
export function parseSave(text) {
  return parse(text.replace(/^\uFEFF/, ''), null, (literal) => {
    const number = Number(literal)
    return String(number) === literal && (!Number.isInteger(number) || Number.isSafeInteger(number))
      ? number
      : new LosslessNumber(literal)
  })
}

export const serializeSave = stringify
export const cloneSave = (value) => parseSave(serializeSave(value))

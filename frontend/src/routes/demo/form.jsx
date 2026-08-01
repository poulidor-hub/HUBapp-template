import React from 'react'
import FormDemo from '../../components/demo/FormDemo'
import { TanStackFormDevtools } from '@tanstack/react-form-devtools'

export default function FormDemoPage() {
  return (
    <>
      <FormDemo />
      {import.meta.env.DEV && (
        <TanStackFormDevtools position="bottom-left" />
      )}
    </>
  )
}

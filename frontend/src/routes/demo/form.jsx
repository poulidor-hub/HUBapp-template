import FormDemo from '../../components/demo/FormDemo'
import { FormDevtoolsPanel } from '@tanstack/react-form-devtools'

export default function FormDemoPage() {
  return (
    <>
      <FormDemo />
      {import.meta.env.DEV && (
        <FormDevtoolsPanel position="bottom-left" />
      )}
    </>
  )
}

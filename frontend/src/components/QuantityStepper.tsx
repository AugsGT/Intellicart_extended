import './QuantityStepper.css'

interface QuantityStepperProps {
  quantity: number
  max: number
  onChange: (quantity: number) => void
}

function QuantityStepper({ quantity, max, onChange }: QuantityStepperProps) {
  return (
    <div className="quantity-stepper">
      <button
        type="button"
        onClick={() => onChange(quantity - 1)}
        disabled={quantity <= 1}
        aria-label="Decrease quantity"
      >
        −
      </button>
      <span className="quantity-value">{quantity}</span>
      <button
        type="button"
        onClick={() => onChange(quantity + 1)}
        disabled={quantity >= max}
        aria-label="Increase quantity"
      >
        +
      </button>
    </div>
  )
}

export default QuantityStepper

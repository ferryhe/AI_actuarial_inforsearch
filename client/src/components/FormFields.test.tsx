import axe from "axe-core";
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CheckboxField, FormField, InputField, SelectField } from "./FormFields";

describe("FormField", () => {
  it("associates its visible label and help text with native controls", async () => {
    const { container } = render(
      <>
        <FormField label="URL" hint="Use HTTPS">
          <InputField value="" onChange={() => undefined} testId="input-url" />
        </FormField>
        <FormField label="Mode">
          <SelectField value="fast" onChange={() => undefined} testId="select-mode" options={[{ value: "fast", label: "Fast" }]} />
        </FormField>
      </>,
    );

    expect(screen.getByLabelText("URL")).toHaveAttribute("aria-describedby", "hint-input-url");
    expect(screen.getByText("Use HTTPS")).toHaveAttribute("id", "hint-input-url");
    expect(screen.getByLabelText("Mode")).toHaveAttribute("id", "select-mode");
    expect((await axe.run(container, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
  });

  it("does not point labels at a checkbox wrapper or a button", () => {
    const { container } = render(
      <>
        <FormField label="Enabled"><CheckboxField checked={false} onChange={() => undefined} label="Enabled" testId="checkbox-enabled" /></FormField>
        <FormField label="Action"><button type="button" data-testid="button-action">Action</button></FormField>
      </>,
    );

    expect(container.querySelector('label[for="checkbox-enabled"]')).toBeNull();
    expect(container.querySelector('label[for="button-action"]')).toBeNull();
    expect(screen.getByLabelText("Enabled")).toHaveAttribute("data-testid", "checkbox-enabled");
  });
});

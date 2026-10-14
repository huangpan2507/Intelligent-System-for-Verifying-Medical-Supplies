import { render, screen, waitFor } from "@testing-library/react";
import type { ComponentProps } from "react";
import Icon from "../index";

jest.unmock("@/components/common/genericIconComponent");

function MockIcon({
  isDark: _isDark,
  ...props
}: ComponentProps<"svg"> & { isDark?: boolean }) {
  return <svg {...props} data-loaded="true" />;
}

const mockGetCachedIcon = jest.fn((): typeof MockIcon | undefined => undefined);
const mockGetNodeIcon = jest.fn(
  async (): Promise<typeof MockIcon | undefined> => MockIcon,
);

jest.mock("@/utils/styleUtils", () => ({
  getCachedIcon: () => mockGetCachedIcon(),
  getNodeIcon: () => mockGetNodeIcon(),
}));

describe("functional icons", () => {
  beforeEach(() => {
    mockGetCachedIcon.mockReturnValue(undefined);
    mockGetNodeIcon.mockResolvedValue(MockIcon);
  });

  it("stores an asynchronously loaded function without invoking it as a state updater", async () => {
    render(<Icon name="FunctionIcon" />);
    await waitFor(() =>
      expect(screen.getByTestId("icon-FunctionIcon")).toHaveAttribute(
        "data-loaded",
        "true",
      ),
    );
  });

  it("stores a cached function without invoking it as a state initializer", async () => {
    mockGetCachedIcon.mockReturnValue(MockIcon);
    render(<Icon name="CachedFunctionIcon" />);
    await waitFor(() =>
      expect(screen.getByTestId("icon-CachedFunctionIcon")).toHaveAttribute(
        "data-loaded",
        "true",
      ),
    );
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { api } from "@/controllers/API/api";
import BusinessResultEvidence from "../BusinessResultEvidence";

jest.mock("@/controllers/API/api", () => ({ api: { get: jest.fn() } }));

it("reuses saved evidence when the summary and settlement group mount in sequence", async () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const get = jest.mocked(api.get);
  get.mockResolvedValue({
    data: {
      counts: { settlement: 0, study: 0, series: 0, image: 0, recognition: 0 },
      items: [],
      total: 0,
    },
  });
  const { unmount } = render(
    <QueryClientProvider client={client}>
      <BusinessResultEvidence taskId="saved-task" resultId="saved-result" />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByText("Sources and evidence"));
  await screen.findByText(/Settlement details · 0/);
  await waitFor(() => expect(client.isFetching()).toBe(0));
  expect(
    get.mock.calls.filter(([url]) => url.includes("group=settlement")),
  ).toHaveLength(1);
  fireEvent.click(screen.getByText("Sources and evidence"));
  fireEvent.click(screen.getByText("Sources and evidence"));
  await waitFor(() => expect(client.isFetching()).toBe(0));
  expect(
    get.mock.calls.filter(([url]) => url.includes("group=settlement")),
  ).toHaveLength(1);
  unmount();
  client.clear();
});

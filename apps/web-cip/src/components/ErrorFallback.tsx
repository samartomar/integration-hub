import { useRouteError, isRouteErrorResponse, useNavigate } from "react-router-dom";

export function ErrorFallback() {
  const error = useRouteError();
  const navigate = useNavigate();

  const is404 =
    isRouteErrorResponse(error) && error.status === 404 ||
    (error instanceof Error && (error.message.includes("404") || error.message.includes("Not Found")));

  const message = isRouteErrorResponse(error)
    ? error.statusText || `${error.status}`
    : error instanceof Error
      ? error.message
      : "Something went wrong";

  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] p-8 text-center">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">
        {is404 ? "Page Not Found" : "Something went wrong"}
      </h1>
      <p className="text-gray-600 mb-6 max-w-md">{message}</p>
      <div className="flex gap-4">
        <button
          onClick={() => navigate(-1)}
          className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
        >
          Go back
        </button>
        <button
          onClick={() => navigate("/admin/dashboard")}
          className="px-4 py-2 text-sm font-medium text-white bg-slate-600 hover:bg-slate-700 rounded-lg"
        >
          Go to Dashboard
        </button>
      </div>
    </div>
  );
}

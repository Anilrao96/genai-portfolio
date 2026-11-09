from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware


def boundaries(app,csp):
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','[::1]'])
    @app.middleware('http')
    async def guard(request:Request,call_next):
        if request.method in ('POST','PATCH','DELETE'):
            origin=request.headers.get('origin')
            if origin and origin!=str(request.base_url).rstrip('/'):
                return JSONResponse({'detail':'Cross-origin requests are refused.'},status_code=403)
            chunks=[];size=0
            async for chunk in request.stream():
                size+=len(chunk)
                if size>10000:return JSONResponse({'detail':'Request is too large.'},status_code=413)
                chunks.append(chunk)
            request._body=b''.join(chunks)
        response=await call_next(request)
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':csp,'Referrer-Policy':'no-referrer'})
        return response

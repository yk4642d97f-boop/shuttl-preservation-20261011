// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "EnduranceDriver",
    platforms: [.macOS(.v14)],
    dependencies: [
        .package(path: "../../../iOS/Packages/ShuttlLive"),
        .package(path: "../../../iOS/Packages/ShuttlAnalysis"),
        .package(path: "../../../iOS/Packages/ShuttlRuntime"),
        .package(path: "../../../iOS/Packages/ShuttlCore"),
    ],
    targets: [
        .executableTarget(name: "EnduranceDriver", dependencies: [
            .product(name: "ShuttlLive", package: "ShuttlLive"),
            .product(name: "ShuttlAnalysis", package: "ShuttlAnalysis"),
            .product(name: "ShuttlRuntime", package: "ShuttlRuntime"),
            .product(name: "ShuttlCore", package: "ShuttlCore"),
        ]),
    ]
)
